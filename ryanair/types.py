from collections import namedtuple

Flight = namedtuple(
    "Flight",
    (
        "departureTime",
        "flightNumber",
        "price",
        "currency",
        "origin",
        "originFull",
        "destination",
        "destinationFull",
    ),
)

FlightV2 = namedtuple(
    "FlightV2",
    (
        "departureTime_local",
        "departureTime_utc",
        "arrivalTime_local",
        "arrivalTime_utc",
        "flightNumber",
        "operatedBy",
        "duration",
        "actualFare",
        "publishedFare",
        "hasDiscount",
        "discountInPercent",
        "hasPromoDiscount",
        "hasBogof",
        "infantsLeft",
        "faresLeft",
        "currency",
        "origin",
        "originFull",
        "destination",
        "destinationFull",

    ),
)

Trip = namedtuple("Trip", ("totalPrice", "outbound", "inbound"))
