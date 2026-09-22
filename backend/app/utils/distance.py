from typing import Optional


# Haversine formula to calculate straight-line distance in kilometers
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> Optional[float]:
    """
    Calculate the great-circle distance between two points on the Earth's surface.
    Returns the distance in kilometers, or None if any coordinate is None.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None

    # Convert decimal degrees to radians
    from math import atan2, cos, radians, sin, sqrt

    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    radius_of_earth_km = 6371.0  # Mean radius in kilometers
    distance = radius_of_earth_km * c
    return distance
