"""Removing hidden data from JPEG files (a copy of kolibri_games/photos.py's strip_jpeg_metadata; keep them the same)."""


def strip_jpeg_metadata(data):
    """A JPEG without its APP1-APP15 and comment segments (EXIF with GPS, XMP, ...).

    Only the hidden data before the image itself is removed; the picture is
    not re-encoded, so this is fast and lossless. Anything that isn't a
    well-formed JPEG is returned unchanged.
    """
    if data[:2] != b"\xff\xd8":
        return data
    out = [data[:2]]
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            return data  # not what we expected: leave it alone
        marker = data[i + 1]
        if marker == 0xDA:  # start of the image data: keep the rest as it is
            out.append(data[i:])
            return b"".join(out)
        length = (data[i + 2] << 8) | data[i + 3]
        segment = data[i:i + 2 + length]
        if not (0xE1 <= marker <= 0xEF or marker == 0xFE):
            out.append(segment)  # keep JFIF (APP0), tables, frame headers
        i += 2 + length
    return data
