"""Stable geographical identity; names are display data, never primary keys."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorldCity:
    city_id: str
    name_ar: str
    name_en: str
    country_ar: str
    country_en: str
    zone: str
    aliases: tuple[str, ...] = ()
    admin_ar: str = ''
    admin_en: str = ''
    note_ar: str = ''
    note_en: str = ''

    def __post_init__(self):
        if not self.city_id.isascii() or not self.city_id.isdecimal() or not all((self.name_ar,self.name_en,self.country_ar,self.country_en,self.zone)):
            raise ValueError('World city is missing a stable ID, localized name or timezone')
        if not any(0x0620<=ord(c)<=0x064a for c in self.name_ar):
            raise ValueError('Arabic city name is not Arabic')
        if any(len(text)>240 or '\x00' in text for text in (self.name_ar,self.name_en,self.country_ar,self.country_en,self.zone)):
            raise ValueError('Invalid city text')

    def name(self, language):
        name=self.name_ar if language == 'ar' else self.name_en
        admin=self.admin_ar if language=='ar' else self.admin_en
        return name+(', '+admin if admin else '')

    def label(self, language):
        name=self.name(language)
        country=self.country_ar if language=='ar' else self.country_en
        note=self.note_ar if language=='ar' else self.note_en
        return f'{name} ({country})'+(f', {note}' if note else '')
