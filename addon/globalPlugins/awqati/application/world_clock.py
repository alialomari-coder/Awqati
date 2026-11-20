"""Offline catalog search, transactional selection and instant-based world time."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import unicodedata
from ..domain.world_clock import WorldCity
from ..domain import ClockReading, ClockType
from .settings_preview import clock_formatter, clock_options


def normalize(value):
    value=unicodedata.normalize('NFKD',value).casefold()
    value=''.join(c for c in value if not unicodedata.combining(c)).translate(str.maketrans('أإآٱى','ااااي')).replace('ـ','')
    return ''.join(value.split())


def validate_display_name(value):
    """Display text only; forbid controls/bidi overrides and bound storage size."""
    if not isinstance(value,str):raise ValueError('Invalid display name')
    if any(unicodedata.category(c).startswith('C') or c in '\u2028\u2029' for c in value):
        raise ValueError('Invalid display name')
    value=value.strip()
    if not value or len(value)>160:
        raise ValueError('Invalid display name')
    return value


class WorldCatalog:
    def __init__(self, cities, version):
        self.cities={c.city_id:c for c in cities}
        if len(self.cities)!=len(cities):raise ValueError('Duplicate geographical ID')
        self.version=version
        self.index={key:tuple(normalize(s) for s in (c.name_ar,c.name_en,*c.aliases)) for key,c in self.cities.items()}
        self.ordered={lang:tuple(sorted(cities,key=lambda c:(normalize(c.name(lang)),normalize(c.label(lang)),c.city_id))) for lang in ('ar','en')}

    def search(self, query='', language='en'):
        needle=normalize(query)
        return tuple(c for c in self.ordered[language] if not needle or any(needle in name for name in self.index[c.city_id]))


class WorldClockService:
    def __init__(self, catalog, repository):
        self.catalog,self.repository=catalog,repository
        data=repository.load()
        self.rows=()
        self.display_names={}
        if data is not None:
            if not isinstance(data,dict) or data.get('schemaVersion')!=1 or not isinstance(data.get('cities'),list):
                raise ValueError('Invalid world-clock user file; existing data must be preserved')
            rows=[];seen=set()
            for record in data['cities']:
                record=dict(record);record['aliases']=tuple(record.get('aliases',()))
                old=WorldCity(**record)
                if old.city_id in seen:raise ValueError('Duplicate selected geographical ID')
                seen.add(old.city_id)
                # An unknown ID retains its previous record instead of vanishing.
                rows.append(catalog.cities.get(old.city_id,old))
            self.rows=tuple(rows)
            custom=data.get('displayNames',{})
            if not isinstance(custom,dict):raise ValueError('Invalid display names')
            for city_id,languages in custom.items():
                if city_id not in seen or not isinstance(languages,dict):raise ValueError('Invalid display identity')
                self.display_names[city_id]={}
                for language,names in languages.items():
                    if language not in ('ar','en') or not isinstance(names,dict) or not set(names)<={'city','country'}:
                        raise ValueError('Invalid display language')
                    self.display_names[city_id][language]={key:validate_display_name(value) for key,value in names.items()}

    def _commit(self, rows, display_names=None):
        rows=tuple(rows)
        custom=self.display_names if display_names is None else display_names
        custom={c.city_id:custom[c.city_id] for c in rows if c.city_id in custom}
        document={'schemaVersion':1,'cities':[asdict(c) for c in rows]}
        if custom:document['displayNames']=custom
        self.repository.save(document)
        self.rows=rows
        self.display_names=custom

    def names(self, city, language):
        reference=(city.name_ar,city.country_ar) if language=='ar' else (city.name_en,city.country_en)
        custom=self.display_names.get(city.city_id,{}).get(language,{})
        return custom.get('city',reference[0]),custom.get('country',reference[1])

    def display(self, city, language):
        name,country=self.names(city,language)
        admin=city.admin_ar if language=='ar' else city.admin_en
        return name+(', '+admin if admin else ''),country

    def edit_names(self, city_id, language, city_name, country_name):
        if language not in ('ar','en'):raise ValueError('Unsupported display language')
        city=next((c for c in self.rows if c.city_id==city_id),None)
        if city is None:raise ValueError('City is no longer selected')
        values=(validate_display_name(city_name),validate_display_name(country_name))
        reference=(city.name_ar,city.country_ar) if language=='ar' else (city.name_en,city.country_en)
        names={key:value for key,value,original in zip(('city','country'),values,reference) if value!=original}
        custom={key:dict(languages) for key,languages in self.display_names.items()}
        languages=custom.setdefault(city_id,{})
        if names:languages[language]=names
        else:languages.pop(language,None)
        if not languages:custom.pop(city_id,None)
        self._commit(self.rows,custom)

    def add(self, city):
        if any(c.city_id==city.city_id for c in self.rows):return False
        self._commit((*self.rows,city));return True

    def delete(self, index):
        if not 0<=index<len(self.rows):raise IndexError(index)
        self._commit(self.rows[:index]+self.rows[index+1:])

    def move(self, index, step):
        target=index+step
        if step not in (-1,1) or not 0<=index<len(self.rows) or not 0<=target<len(self.rows):return index
        rows=list(self.rows);rows[index],rows[target]=rows[target],rows[index]
        self._commit(rows);return target

    def first(self, index):
        return self.rows[index] if 0<=index<len(self.rows) else None


def arabic_duration(minutes):
    hours,minutes=divmod(minutes,60)
    def unit(n,singular,dual,plural):
        if n==1:return singular
        if n==2:return dual
        words={3:'ثلاث',4:'أربع',5:'خمس',6:'ست',7:'سبع',8:'ثمان',9:'تسع',10:'عشر'}
        return f'{words[n]} {plural}' if n in words else f'{n} '+('ساعة' if singular.startswith('ساعة') else 'دقيقة')
    parts=[]
    if hours:parts.append(unit(hours,'ساعة واحدة','ساعتين','ساعات'))
    if minutes:parts.append(unit(minutes,'دقيقة واحدة','دقيقتين','دقائق'))
    return ' و'.join(parts)


def describe_city(city, instant, zones, local_zone, language, presentation, display_names=None):
    if instant.tzinfo is None or instant.utcoffset() is None:raise ValueError('An aware instant is required')
    instant=instant.astimezone(timezone.utc)
    value=instant.astimezone(zones.get_timezone(city.zone))
    local=instant.astimezone(local_zone)
    delta=int((value.utcoffset()-local.utcoffset()).total_seconds()/60)
    reading=ClockReading(value,timedelta(),value)
    time_text=clock_formatter(language,presentation.representation).format_time(reading,ClockType.ZAWALI,clock_options(presentation))
    name=city.name(language)
    if display_names is not None:name=f'{display_names[0]} ({display_names[1]})'
    if language=='ar':
        day=('الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت','الأحد')[value.weekday()]
        difference=('موافقة لتوقيتك المحلي' if delta==0 else
            ('متقدمة على توقيتك المحلي ب' if delta>0 else 'متأخرة عن توقيتك المحلي ب')+arabic_duration(abs(delta)))
        result=f'{name}، الساعة {time_text} من يوم {day}، {difference}'
    else:
        day=('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')[value.weekday()]
        h,m=divmod(abs(delta),60)
        duration=' and '.join(p for p in (f'{h} hour'+('s' if h!=1 else '') if h else '', f'{m} minute'+('s' if m!=1 else '') if m else '') if p)
        difference='same as your local time' if delta==0 else f'{duration} '+('ahead of' if delta>0 else 'behind')+' your local time'
        result=f'{name}, {time_text} on {day}, {difference}'
    note=city.note_ar if language=='ar' else city.note_en
    if note:result+=('، ' if language=='ar' else ', ')+note
    if city.city_id not in getattr(zones,'catalog_ids', {city.city_id}):
        result+=('، تحتاج بيانات المدينة إلى مراجعة' if language=='ar' else ', city data needs review')
    return result
