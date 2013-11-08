from datetime import timedelta
from .interchange import WaypointType

class ActivityStatisticCalculator:
    ImplicitPauseTime = timedelta(minutes=1, seconds=5)

    def CalculateDistance(act, startWpt=None, endWpt=None):
        import math
        dist = 0
        altHold = None  # seperate from the lastLoc variable, since we want to hold the altitude as long as required
        lastTimestamp = lastLoc = None

        if not startWpt:
            startWpt = act.Waypoints[0]
        if not endWpt:
            endWpt = act.Waypoints[-1]

        for x in range(act.Waypoints.index(startWpt), act.Waypoints.index(endWpt) + 1):
            timeDelta = act.Waypoints[x].Timestamp - lastTimestamp if lastTimestamp else None
            lastTimestamp = act.Waypoints[x].Timestamp

            if act.Waypoints[x].Type == WaypointType.Pause or (timeDelta and timeDelta > ActivityStatisticCalculator.ImplicitPauseTime):
                lastLoc = None  # don't count distance while paused
                continue

            loc = act.Waypoints[x].Location
            if loc is None or loc.Longitude is None or loc.Latitude is None:
                # Used to throw an exception in this case, but the TCX schema allows for location-free waypoints, so we'll just patch over it.
                continue

            if loc and lastLoc:
                altHold = lastLoc.Altitude if lastLoc.Altitude is not None else altHold
                latRads = loc.Latitude * math.pi / 180
                meters_lat_degree = 1000 * 111.13292 + 1.175 * math.cos(4 * latRads) - 559.82 * math.cos(2 * latRads)
                meters_lon_degree = 1000 * 111.41284 * math.cos(latRads) - 93.5 * math.cos(3 * latRads)
                dx = (loc.Longitude - lastLoc.Longitude) * meters_lon_degree
                dy = (loc.Latitude - lastLoc.Latitude) * meters_lat_degree
                if loc.Altitude is not None and altHold is not None:  # incorporate the altitude when possible
                    dz = loc.Altitude - altHold
                else:
                    dz = 0
                dist += math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
            lastLoc = loc

        return dist

    def CalculateMovingTime(act, startWpt=None, endWpt=None):
        if len(act.Waypoints) < 3:
            # Either no waypoints, or one at the start and one at the end
            raise ValueError("Not enough waypoints to calculate moving time")
        duration = timedelta(0)
        if not startWpt:
            startWpt = act.Waypoints[0]
        if not endWpt:
            endWpt = act.Waypoints[-1]
        lastTimestamp = None
        for x in range(act.Waypoints.index(startWpt), act.Waypoints.index(endWpt) + 1):
            wpt = act.Waypoints[x]
            delta = wpt.Timestamp - lastTimestamp if lastTimestamp else None
            lastTimestamp = wpt.Timestamp
            if wpt.Type is WaypointType.Pause:
                lastTimestamp = None
            elif delta and delta > act.ImplicitPauseTime:
                delta = None  # Implicit pauses
            if delta:
                duration += delta
        if duration.total_seconds() == 0 and startWpt is None and endWpt is None:
            raise ValueError("Zero-duration activity")
        return duration
