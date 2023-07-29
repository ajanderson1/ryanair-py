import os
from collections import namedtuple
from math import radians, sin, cos, asin, sqrt

import csv

from ryanair.types import Flight

Airport = namedtuple("Airport", ("IATA_code", "name", "lat", "lng", "location", "municipality", "iso_region", "iso_country"))

AIRPORTS = {}
with open(
    os.path.join(os.path.dirname(__file__), "airports.csv"), newline="", encoding="utf8"
) as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        iata_code = row["iata_code"]
        name = row["name"]
        location = ",".join((row["iso_region"], row["iso_country"]))
        municipality = row["municipality"]
        lat = float(row["latitude_deg"])
        lng = float(row["longitude_deg"])
        iso_region = row["iso_region"]
        iso_country = row["iso_country"]

        AIRPORTS[iata_code] = Airport(
            IATA_code=iata_code, name=name, lat=lat, lng=lng, location=location, municipality=municipality, iso_region=iso_region, iso_country=iso_country
        )

def get_airport_by_iata(iata_code):
    return f"{AIRPORTS[iata_code].name}, {AIRPORTS[iata_code].municipality}"


def validate_airport(iata_code)->bool:
    """
    Check if the airport is valid, ie. a valid IATA code
    """
    return iata_code in AIRPORTS



def _haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in kilometers between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers.
    return c * r


def get_flight_distance(flight: Flight):
    return get_distance_between_airports(flight.origin, flight.destination)


def get_distance_between_airports(iata_a, iata_b):
    a, b = AIRPORTS[iata_a], AIRPORTS[iata_b]
    return _haversine(a.lat, a.lng, b.lat, b.lng)
