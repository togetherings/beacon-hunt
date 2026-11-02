"""
A small reader for Mapbox Vector Tiles (the format of Mapillary's coverage tiles).

Only what the pack tool needs: layer names, each feature's properties and its
points (for lines, every vertex), turned into longitude and latitude. No
protobuf library needed: the format is simple enough to read by hand.
See https://github.com/mapbox/vector-tile-spec (version 2).
"""
import gzip
import struct
import math


def _varint(buf, i):
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def _fields(buf):
    """(field number, wire type, value) for each field in a protobuf message."""
    i, n = 0, len(buf)
    while i < n:
        key, i = _varint(buf, i)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 1:
            value, i = buf[i:i + 8], i + 8
        elif wire == 2:
            length, i = _varint(buf, i)
            value, i = buf[i:i + length], i + length
        elif wire == 5:
            value, i = buf[i:i + 4], i + 4
        else:
            raise ValueError("unsupported protobuf wire type %d" % wire)
        yield field, wire, value


def _packed(buf):
    out, i = [], 0
    while i < len(buf):
        v, i = _varint(buf, i)
        out.append(v)
    return out


def _zigzag(n):
    return (n >> 1) ^ -(n & 1)


def _value(buf):
    for field, _wire, v in _fields(buf):
        if field == 1:
            return bytes(v).decode("utf-8", "replace")
        if field == 2:
            return struct.unpack("<f", bytes(v))[0]
        if field == 3:
            return struct.unpack("<d", bytes(v))[0]
        if field in (4, 5):
            return v if v < (1 << 63) else v - (1 << 64)
        if field == 6:
            return _zigzag(v)
        if field == 7:
            return bool(v)
    return None


def _geometry(cmds):
    """The points of a feature's geometry, in tile units (every vertex of lines and polygons)."""
    points, x, y, i = [], 0, 0, 0
    while i < len(cmds):
        cmd, count = cmds[i] & 7, cmds[i] >> 3
        i += 1
        if cmd in (1, 2):  # MoveTo, LineTo
            for _ in range(count):
                x += _zigzag(cmds[i])
                y += _zigzag(cmds[i + 1])
                i += 2
                points.append((x, y))
        # ClosePath (7) has no parameters
    return points


def looks_valid(data):
    """Is this a vector tile? (An empty tile is fine.) Catches error pages saved by mistake."""
    try:
        data = bytes(data)
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        for field, wire, _value in _fields(memoryview(data)):
            if field != 3 or wire != 2:  # a tile holds only layers (field 3)
                return False
        return True
    except (ValueError, IndexError, OSError, EOFError):
        return False


def decode(data, z, tx, ty, layers=None):
    """{layer name: [(properties, [(lon, lat), ...]), ...]} for one tile."""
    data = bytes(data)
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    data = memoryview(data)
    out = {}
    for field, _wire, layer_buf in _fields(data):
        if field != 3:
            continue
        name, keys, values, features, extent = None, [], [], [], 4096
        for f, _w, v in _fields(layer_buf):
            if f == 1:
                name = bytes(v).decode("utf-8")
            elif f == 2:
                features.append(v)
            elif f == 3:
                keys.append(bytes(v).decode("utf-8"))
            elif f == 4:
                values.append(_value(v))
            elif f == 5:
                extent = v
        if layers is not None and name not in layers:
            continue
        found = []
        for feat in features:
            tags, geom = [], []
            for f, _w, v in _fields(feat):
                if f == 2:
                    tags = _packed(v)
                elif f == 4:
                    geom = _packed(v)
            props = {keys[tags[j]]: values[tags[j + 1]] for j in range(0, len(tags) - 1, 2)}
            found.append((props, [tile_to_lon_lat(z, tx, ty, px / extent, py / extent) for px, py in _geometry(geom)]))
        out.setdefault(name, []).extend(found)
    return out


def tile_to_lon_lat(z, tx, ty, fx=0.0, fy=0.0):
    """Longitude and latitude of a point in a Web Mercator tile (fx, fy from 0 to 1 across the tile)."""
    n = 2.0 ** z
    lon = (tx + fx) / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ty + fy) / n))))
    return lon, lat


def tiles_for_bbox(z, south, west, north, east):
    """The (x, y) of every tile at zoom z that covers a box in degrees."""
    def tile_x(lon):
        return int((lon + 180.0) / 360.0 * 2 ** z)

    def tile_y(lat):
        lat = max(-85.0511, min(85.0511, lat))
        r = math.radians(lat)
        return int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2 ** z)

    top = 2 ** z - 1
    for x in range(max(0, tile_x(west)), min(top, tile_x(east)) + 1):
        for y in range(max(0, tile_y(north)), min(top, tile_y(south)) + 1):
            yield x, y


# ------------------------------------------------------------------ writing (for tests)


def _enc_varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _enc_field(field, wire, payload):
    if wire == 0:
        return _enc_varint(field << 3) + _enc_varint(payload)
    return _enc_varint(field << 3 | 2) + _enc_varint(len(payload)) + payload


def encode(layers, extent=4096):
    """A tile from {layer: [(properties, [(px, py) in tile units], geometry type)]}. Used by the tests' fake Mapillary."""
    tile = b""
    for name, features in layers.items():
        keys, values, body = [], [], b""
        for props, points, gtype in features:
            tags = []
            for k, v in props.items():
                if k not in keys:
                    keys.append(k)
                if v not in values:
                    values.append(v)
                tags += [keys.index(k), values.index(v)]
            cmds, x, y = [], 0, 0
            for i, (px, py) in enumerate(points):
                if i == 0:
                    cmds.append(1 | (1 << 3))
                elif i == 1:
                    cmds.append(2 | ((len(points) - 1) << 3))
                cmds += [((px - x) << 1) ^ ((px - x) >> 31), ((py - y) << 1) ^ ((py - y) >> 31)]
                x, y = px, py
            feat = _enc_field(2, 2, b"".join(_enc_varint(t) for t in tags))
            feat += _enc_field(3, 0, gtype)
            feat += _enc_field(4, 2, b"".join(_enc_varint(c & 0xFFFFFFFF) for c in cmds))
            body += _enc_field(2, 2, feat)
        layer = _enc_field(15, 0, 2) + _enc_field(1, 2, name.encode())
        layer += body
        layer += b"".join(_enc_field(3, 2, k.encode()) for k in keys)
        for v in values:
            if isinstance(v, bool):
                val = _enc_field(7, 0, int(v))
            elif isinstance(v, int):
                val = _enc_field(4, 0, v if v >= 0 else v + (1 << 64))
            else:
                val = _enc_field(1, 2, str(v).encode())
            layer += _enc_field(4, 2, val)
        layer += _enc_field(5, 0, extent)
        tile += _enc_field(3, 2, layer)
    return tile
