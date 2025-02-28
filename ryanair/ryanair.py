"""
This module allows you to retrieve either
1) the cheapest flights, with or without return flights, within a fixed set of dates.
or
2) all available flights between two locations, on a given date
This is done directly through Ryanair's API, and does not require an API key.
"""
import logging
from datetime import datetime, date, time
from typing import Union, Optional

import backoff
import requests
from deprecated import deprecated

from free_proxy import get_first_operational_proxy

from ryanair.types import Flight, FlightV2, Trip
from ryanair.airport_utils import get_airport_by_iata

logger = logging.getLogger(__name__)

# if not logger.handlers:
#     logger.setLevel(logging.INFO)

#     console_handler = logging.StreamHandler()
#     formatter = logging.Formatter(
#         "%(asctime)s.%(msecs)03d %(levelname)s:%(message)s", datefmt="%Y-%m-%d %I:%M:%S"
#     )

#     console_handler.setFormatter(formatter)
#     logger.addHandler(console_handler)

proxy = None


class RyanairException(Exception):
    def __init__(self, message):
        super().__init__(f"Ryanair API: {message}")


class AvailabilityException(RyanairException):
    def __init__(self):
        super().__init__("Availability API declined to provide a result")


# noinspection PyBroadException
class Ryanair:
    BASE_SERVICES_API_URL = "https://services-api.ryanair.com/farfnd/v4/"
    BASE_AVAILABILITY_API_URL = "https://www.ryanair.com/api/booking/v4/"
    BASE_SITE_FOR_SESSION_URL = "https://www.ryanair.com/"
    # Further API endpoints:
    RYANAIR_SCHEDULES_ENDPOINT = "https://www.ryanair.com/api/timtbl/3/schedules/{fromCode}/periods"
    RYANAIR_SCHEDULED_DATES_FOR_ROUTE_ENDPOINT = "https://www.ryanair.com/api/farfnd/v4/oneWayFares/{fromCode}/{toCode}/availabilities"
    RYANAIR_ACTIVE_AIRPORTS = "https://www.ryanair.com/api/views/locate/5/airports/en/active"
    RYANAIR_DESTINATION_AIRPORTS = "https://www.ryanair.com/api/views/locate/searchWidget/routes/en/airport/{fromCode}"

    def __init__(self, currency: Optional[str] = None):
        self.currency = currency

        self._num_queries = 0
        self.session = requests.Session()
        self._update_session_cookie()

    def get_active_airports(self) -> list:
        """
        Uses the Ryanair API Endpoint: https://www.ryanair.com/api/views/locate/5/airports/en/active to get
        the active airports for a given airport code.

        :return: A list of active airports for the given airport code.
        """

        # Prepare the query URL
        query_url = Ryanair.RYANAIR_ACTIVE_AIRPORTS

        try:
            # Query the API
            response = self._retryable_query(query_url, {})
        except Exception as e:
            logger.exception(f"Failed to parse response when querying {query_url}")
            return []

        # If response exists, return it
        if response:
            return response

        return []


    def get_destinations(self, from_code: str) -> list:
        """
        Uses the Ryanair API Endpoint: https://www.ryanair.com/api/views/locate/searchWidget/routes/en/airport/{{fromCode}} to get
        the destinations for a given airport code.

        :param from_code: The airport code to get the destinations for.
        :return: A list of destinations for the given airport code.
        """

        # Prepare the query URL
        query_url = Ryanair.RYANAIR_DESTINATION_AIRPORTS.format(fromCode=from_code)

        try:
            # Query the API
            response = self._retryable_query(query_url, {})
        except Exception as e:
            logger.exception(f"Failed to parse response when querying {query_url}")
            return []

        # If response exists, return it
        if response:
            return response

        return []



    def get_flight_schedules(self, from_code: str):
        """
        Uses the Ryanair API Endpoint: https://www.ryanair.com/api/timtbl/3/schedules/{{fromCode}}/periods to get
        the flight schedules for a given airport code.

        :param from_code: The airport code to get the flight schedules for.
        :return: A list of flight schedules for the given airport code.
        """

        # Prepare the query URL
        query_url = Ryanair.RYANAIR_SCHEDULES_ENDPOINT.format(fromCode=from_code)

        try:
            # Query the API
            response = self._retryable_query(query_url, {})
        except Exception as e:
            logger.exception(f"Failed to parse response when querying {query_url}")
            return []

        # If response exists, return it
        if response:
            return response

        return []

    def get_scheduled_dates_for_route(self, from_code: str, to_code: str):
        """
        Uses the Ryanair API Endpoint: https://www.ryanair.com/api/farfnd/v4/oneWayFares/{{fromCode}}/{{toCode}}/availabilities to get
        the available flights for a given airport code.

        :param from_code: The airport code to get the available flights from.
        :param to_code: The airport code to get the available flights to.
        :return: A list of available flights for the given airport codes.

        NB: This API Endpoint does not consider when flights are 'sold out' on that they are scheduled.
        """

        #  Prepare the query URL
        query_url = Ryanair.RYANAIR_SCHEDULED_DATES_FOR_ROUTE_ENDPOINT.format(fromCode=from_code, toCode=to_code)

        try:
            # Query the API
            response = self._retryable_query(query_url, {})
        except Exception as e:
            logger.exception(f"Failed to parse response when querying {query_url}")
            return []

        # If response exists, return it
        if response:
            return response

        return []

    def get_cheapest_flights(
        self,
        airport: str,
        date_from: Union[datetime, date, str],
        date_to: Union[datetime, date, str],
        destination_country: Optional[str] = None,
        custom_params: Optional[dict] = None,
        departure_time_from: Union[str, time] = "00:00",
        departure_time_to: Union[str, time] = "23:59",
        max_price: Optional[int] = None,
        destination_airport: Optional[str] = None,
    ):
        query_url = "".join((Ryanair.BASE_SERVICES_API_URL, "oneWayFares"))

        params = {
            "departureAirportIataCode": airport,
            "outboundDepartureDateFrom": self._format_date_for_api(date_from),
            "outboundDepartureDateTo": self._format_date_for_api(date_to),
            "outboundDepartureTimeFrom": self._format_time_for_api(departure_time_from),
            "outboundDepartureTimeTo": self._format_time_for_api(departure_time_to),
        }
        if self.currency:
            params["currency"] = self.currency
        if destination_country:
            params["arrivalCountryCode"] = destination_country
        if max_price:
            params["priceValueTo"] = max_price
        if destination_airport:
            params["arrivalAirportIataCode"] = destination_airport
        if custom_params:
            params.update(custom_params)

        try:
            response = self._retryable_query(query_url, params)["fares"]
        except Exception:
            logger.exception(f"Failed to parse response when querying {query_url}")
            return []

        if response:
            return [
                self._parse_cheapest_flight(flight["outbound"]) for flight in response
            ]

        return []

    def get_cheapest_return_flights(
        self,
        source_airport: str,
        date_from: Union[datetime, date, str],
        date_to: Union[datetime, date, str],
        return_date_from: Union[datetime, date, str],
        return_date_to: Union[datetime, date, str],
        destination_country: Optional[str] = None,
        custom_params: Optional[dict] = None,
        outbound_departure_time_from: Union[str, time] = "00:00",
        outbound_departure_time_to: Union[str, time] = "23:59",
        inbound_departure_time_from: Union[str, time] = "00:00",
        inbound_departure_time_to: Union[str, time] = "23:59",
        max_price: Optional[int] = None,
        destination_airport: Optional[str] = None,
    ):
        query_url = "".join((Ryanair.BASE_SERVICES_API_URL, "roundTripFares"))

        params = {
            "departureAirportIataCode": source_airport,
            "outboundDepartureDateFrom": self._format_date_for_api(date_from),
            "outboundDepartureDateTo": self._format_date_for_api(date_to),
            "inboundDepartureDateFrom": self._format_date_for_api(return_date_from),
            "inboundDepartureDateTo": self._format_date_for_api(return_date_to),
            "outboundDepartureTimeFrom": self._format_time_for_api(
                outbound_departure_time_from
            ),
            "outboundDepartureTimeTo": self._format_time_for_api(
                outbound_departure_time_to
            ),
            "inboundDepartureTimeFrom": self._format_time_for_api(
                inbound_departure_time_from
            ),
            "inboundDepartureTimeTo": self._format_time_for_api(
                inbound_departure_time_to
            ),
        }
        if self.currency:
            params["currency"] = self.currency
        if destination_country:
            params["arrivalCountryCode"] = destination_country
        if max_price:
            params["priceValueTo"] = max_price
        if destination_airport:
            params["arrivalAirportIataCode"] = destination_airport
        if custom_params:
            params.update(custom_params)

        try:
            response = self._retryable_query(query_url, params)["fares"]
        except Exception as e:
            logger.exception(f"Failed to parse response when querying {query_url}")
            return []

        if response:
            return [
                self._parse_cheapest_return_flights_as_trip(
                    trip["outbound"], trip["inbound"]
                )
                for trip in response
            ]
        else:
            return []

    def get_all_flights(
        self,
        origin_airport: str,
        date_out: Union[datetime, date, str],
        destination: str,
        # locale: str = "",
        # origin_is_mac: bool = False,
        # destination_is_mac: bool = False,
        custom_params: Optional[dict] = None,
    ):
        """
        This function can be used to get all flights between within a given week.

        With the default parameters, it will return all flights between the origin and destination airports for a single week.  More than that is not supported by the API.

        """


        query_url = "".join(
            (Ryanair.BASE_AVAILABILITY_API_URL, f"/availability")
        )

        params = {
            # Assume single adult ticket only
            "ADT": 1,
            "TEEN": 0,
            "CHD": 0,
            "INF": 0,
            "DateOut": self._format_date_for_api(date_out),
            "DateIn": "",
            "Origin": origin_airport,
            "Destination": destination,
            # "OriginIsMac": origin_is_mac,
            # "DestinationIsMac": destination_is_mac,
            "IncludeConnectingFlights": False,  # What? You do that?
            "ToUs": "AGREED",
            # Presently unused, but these and others can be set by custom_params
            "Disc": 0,
            "promoCode": "",
            "FlexDaysBeforeOut": 0,
            "FlexDaysOut": 6,
            # "FlexDaysBeforeIn": 2,
            # "FlexDaysIn": 2,
            "RoundTrip": False,
        }

        if custom_params:
            params.update(custom_params)

        try:
            # Try once to get a new session cookie, just in case the old one has expired.
            # If that fails too, we should raise the exception.
            response = self._retryable_query(query_url, params)

            if self.check_if_availability_response_is_declined(response):
                logger.warning(
                    "Availability API declined to respond, attempting again with a new session cookie"
                )
                self._update_session_cookie()
                response = self._retryable_query(query_url, params)
                if self.check_if_availability_response_is_declined(response):
                    raise AvailabilityException

            return self._parse_all_flights_availability_result_as_flight_v2(response)

        except RyanairException:
            logger.exception(
                f"Failed to parse response when querying {query_url} with parameters {params}"
            )
            return []
        except Exception:
            logger.exception(
                f"Failed to parse response when querying {query_url} with parameters {params}"
            )
            return []

    @staticmethod
    def check_if_availability_response_is_declined(response: dict) -> bool:
        return "message" in response and response["message"] == "Availability declined"

    @staticmethod
    def _on_query_error(e):
        logger.exception(f"Gave up retrying query, last exception was {e}")

    # CUSTOM BACKOFF HANDLER ======================
    def on_backoff_handler(details):
        try:
            global proxy
            logger.info(f"Requesting a proxy (using free-proxy library)")
            proxy = get_first_operational_proxy()
        except ValueError as e:
            logger.exception(f"Failed to get proxy: {e}, Setting proxy to `None`")
            proxy = None

    # ============================================

    @backoff.on_exception(
        backoff.expo,
        Exception,
        on_backoff=on_backoff_handler,
        max_tries=5,
        logger=logger,
        on_giveup=_on_query_error,
        raise_on_giveup=False,
    )
    def _retryable_query(self, url, params):
        self._num_queries += 1

        # for testing purposes
        # import random
        # if random.randint() % 2 == 0:
        #     raise Exception("random error")

        if proxy:
            logger.warning(f"Ryanair API using proxy: {proxy}")
            # logger.debug(f"Sending request URL: {url} with params: {params}")
            return self.session.get(url, params=params, proxies=proxy).json()
        else:
            # logger.debug("Not using proxy")
            # logger.debug(f"Sending request URL: {url} with params: {params}")
            return self.session.get(url, params=params).json()

    def _update_session_cookie(self):
        # Visit main website to get session cookies
        self.session.get(Ryanair.BASE_SITE_FOR_SESSION_URL)

    def _parse_cheapest_flight(self, flight):
        currency = flight["price"]["currencyCode"]
        if self.currency and self.currency != currency:
            logger.warning(
                f"Requested cheapest flights in {self.currency} but API responded with fares in {currency}"
            )
        return Flight(
            origin=flight["departureAirport"]["iataCode"],
            originFull=", ".join(
                (
                    flight["departureAirport"]["name"],
                    flight["departureAirport"]["countryName"],
                )
            ),
            destination=flight["arrivalAirport"]["iataCode"],
            destinationFull=", ".join(
                (
                    flight["arrivalAirport"]["name"],
                    flight["arrivalAirport"]["countryName"],
                )
            ),
            departureTime=datetime.fromisoformat(flight["departureDate"]),
            flightNumber=f"{flight['flightNumber'][:2]} {flight['flightNumber'][2:]}",
            price=flight["price"]["value"],
            currency=currency,
        )

    def _parse_cheapest_return_flights_as_trip(self, outbound, inbound):
        outbound = self._parse_cheapest_flight(outbound)
        inbound = self._parse_cheapest_flight(inbound)

        return Trip(
            outbound=outbound,
            inbound=inbound,
            totalPrice=inbound.price + outbound.price,
        )

    @staticmethod
    def _parse_all_flights_availability_result_as_flight(
        response, origin_full, destination_full, currency
    ):
        return Flight(
            departureTime=datetime.fromisoformat(response["time"][0]),
            flightNumber=response["flightNumber"],
            price=response["regularFare"]["fares"][0]["amount"]
            if response["faresLeft"] != 0
            else float("inf"),
            currency=currency,
            origin=response["segments"][0]["origin"],
            originFull=origin_full,
            destination=response["segments"][0]["destination"],
            destinationFull=destination_full,
        )

    @staticmethod
    def _parse_all_flights_availability_result_as_flight_v2(response) -> list[FlightV2] | None:
        """
        Parse the response from the Ryanair API into a list of FlightV2 objects
        """

        list_of_flights = []
        currency = response['currency']  # the currency will use the origin airport if allowable otherwise defailt to locale

        try:
            assert len(response['trips']) == 1
        except AssertionError:
            logger.warning(f"There are multiple ({len(response['trips'])}) trips in the response, this is not expected - Cancelling full API call")
            return []

        for this_date in response['trips'][0]['dates']:
            for this_flight in this_date['flights']:
                flight_dict = {}

                # currency
                flight_dict['currency'] = currency

                # faresLeft
                if 'faresLeft' in this_flight:
                    flight_dict['faresLeft'] = this_flight['faresLeft']  # NB: '-1' appears to suggest it doesnt know, ie lots! (not overbooked i dont think)
                    if flight_dict['faresLeft'] == -1:
                        flight_dict['faresLeft'] = None
                else:
                    flight_dict['faresLeft'] = None

                # flightKey
                if 'flightKey' in this_flight:
                    # flight_dict['flightKey'] = this_flight['flightKey'] # can ignore for now as data is duplicated
                    pass

                # infantsLeft
                if 'infantsLeft' in this_flight:
                    flight_dict['infantsLeft'] = this_flight['infantsLeft']
                    if flight_dict['infantsLeft'] == -1:
                        flight_dict['infantsLeft'] = None
                else:
                    flight_dict['infantsLeft'] = None

                # regularFare
                if not 'regularFare' in this_flight:
                    logger.debug(f"No regularFare in this_flight - Sold Out:{this_flight['faresLeft']==0}.  HINT: This will still return a flight, but with no price information")
                    flight_dict.update({key: None for key in ['actualFare', 'publishedFare', 'hasDiscount', 'discountInPercent', 'hasPromoDiscount', 'hasBogof']})
                else:
                    try:
                        assert len(this_flight['regularFare']['fares']) == 1
                        for this_fare in this_flight['regularFare']['fares']:
                            assert this_fare['type'] == 'ADT'
                            flight_dict['actualFare'] = this_fare['amount']
                            flight_dict['publishedFare'] = this_fare['publishedFare']
                            # flight_dict['price'] = this_fare['count'] # ignore
                            flight_dict['hasDiscount'] = this_fare['hasDiscount']
                            flight_dict['discountInPercent'] = this_fare['discountInPercent']
                            flight_dict['hasPromoDiscount'] = this_fare['hasPromoDiscount']
                            flight_dict['hasBogof'] = this_fare['hasBogof']
                    except AssertionError:
                        logger.warning(f"Unexpected fare structure - ignoring entire API call")
                        print(this_flight['regularFare'])
                        continue

                # operatedBy
                if 'operatedBy' in this_flight:
                    flight_dict['operatedBy'] = this_flight['operatedBy']

                # segments
                if 'segments' in this_flight:
                    try:
                        assert len(this_flight['segments']) == 1
                        this_segment = this_flight['segments'][0]

                        # flightNumber
                        if 'flightNumber' in this_segment:
                            flight_dict['flightNumber'] = this_segment['flightNumber']

                        # time
                        if 'time' in this_segment:
                            assert len(this_segment['time']) == 2
                            flight_dict['departureTime_local'] = this_segment['time'][0]
                            flight_dict['arrivalTime_local'] = this_segment['time'][1]
                            # convert to datetime without using pandas
                            # flight_dict['departureTime_local'] = datetime.strptime(flight_dict['departureTime_local'], '%H:%M')
                            # flight_dict['arrivalTime_local'] = datetime.strptime(flight_dict['arrivalTime_local'], '%H:%M')

                        # timeUTC
                        if 'timeUTC' in this_segment:
                            assert len(this_segment['timeUTC']) == 2
                            flight_dict['departureTime_utc'] = this_segment['timeUTC'][0]
                            flight_dict['arrivalTime_utc'] = this_segment['timeUTC'][1]
                            # convert to datetime
                            # flight_dict['departureTime_utc'] = pd.to_datetime(flight_dict['departureTime_utc'])
                            # flight_dict['arrivalTime_utc'] = pd.to_datetime(flight_dict['arrivalTime_utc'])

                        # duration
                        flight_dict['duration'] = this_segment['duration'] if 'duration' in this_flight else None

                        # origin
                        if 'origin' in this_segment:
                            flight_dict['origin'] = this_segment['origin']
                            flight_dict['originFull'] = get_airport_by_iata(this_segment['origin'])
                        else:
                            logger.warning(f"Unexpected origin structure - ignoring this flight")
                            logger.critical(this_flight.keys())
                            continue

                        # destination
                        if 'destination' in this_segment:
                            flight_dict['destination'] = this_segment['destination']
                            flight_dict['destinationFull'] = get_airport_by_iata(this_segment['destination'])
                        else:
                            logger.warning(f"Unexpected destination structure - ignoring this flight")
                            continue

                    except AssertionError:
                        logger.warning(f"Unexpected segments structure - ignoring entire API call")
                        continue
                
                    list_of_flights.append(FlightV2(**flight_dict))

        logger.debug(f"Found {len(list_of_flights)} flights in the response")
        return list_of_flights

    @staticmethod
    def _format_date_for_api(d: Union[datetime, date, str]):
        if isinstance(d, str):
            return d

        if isinstance(d, datetime):
            return d.date().isoformat()

        if isinstance(d, date):
            return d.isoformat()

    @staticmethod
    def _format_time_for_api(t: Union[time, str]):
        if isinstance(t, str):
            return t

        if isinstance(t, time):
            return t.strftime("%H:%M")

    @property
    def num_queries(self):
        return self._num_queries

    @deprecated(
        version="2.0.0",
        reason="deprecated in favour of get_cheapest_flights",
        action="once",
    )
    def get_flights(self, airport, date_from, date_to, destination_country=None):
        return self.get_cheapest_flights(
            airport, date_from, date_to, destination_country
        )

    @deprecated(
        version="2.0.0",
        reason="deprecated in favour of get_cheapest_return_flights",
        action="once",
    )
    def get_return_flights(
        self,
        source_airport,
        date_from,
        date_to,
        return_date_from,
        return_date_to,
        destination_country=None,
    ):
        return self.get_cheapest_return_flights(
            source_airport,
            date_from,
            date_to,
            return_date_from,
            return_date_to,
            destination_country,
        )
