"""Offline coordinate cross-check against pinned, independent OSM timezone polygons."""
from collections import defaultdict
import json
import math
import zipfile


def inside(x, y, ring):
    result = False
    a, b = ring[-1]
    for c, d in ring:
        if (b > y) != (d > y) and x < (c-a)*(y-b)/(d-b)+a:
            result = not result
        a, b = c, d
    return result


class BoundaryIndex:
    def __init__(self, archive):
        with zipfile.ZipFile(archive) as source:
            document = json.loads(source.read('combined.json'))
        self.cells = defaultdict(list)
        self.polygon_count = 0
        for feature in document['features']:
            zone = feature['properties']['tzid']
            geometry = feature['geometry']
            polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
            for polygon in polygons:
                outer = polygon[0]
                x1 = min(p[0] for p in outer); x2 = max(p[0] for p in outer)
                y1 = min(p[1] for p in outer); y2 = max(p[1] for p in outer)
                item = (zone, polygon, (x1,y1,x2,y2))
                for x in range(math.floor(x1), math.floor(x2)+1):
                    for y in range(math.floor(y1), math.floor(y2)+1):
                        self.cells[x,y].append(item)
                self.polygon_count += 1

    def zones(self, latitude, longitude):
        x,y=float(longitude),float(latitude)
        found=set()
        for zone,polygon,(x1,y1,x2,y2) in self.cells[math.floor(x),math.floor(y)]:
            if x1<=x<=x2 and y1<=y<=y2 and inside(x,y,polygon[0]) and not any(inside(x,y,hole) for hole in polygon[1:]):
                found.add(zone)
        return found
