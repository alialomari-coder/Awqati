"""Awqati never searches system paths or imports an external tzdata package."""


def find_tzfile(key):
    raise ValueError('World clock requires checksum-verified ZoneInfo.from_file data')
