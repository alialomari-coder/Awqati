# Overview

Awqati is a free, open-source add-on for the NVDA screen reader. It provides prayer times and related alerts, Zawali and Ghurubi clocks, and five calendars: Gregorian, Lunar Hijri, and three Solar Hijri calendars, as well as date converters, daily astronomical information, and the traditional Arabian calendar.

The add-on also provides current weather conditions and daily and hourly forecasts, Wikipedia's On This Day service, and Qibla direction information. It includes four time management tools: alarms, countdown timers, a stopwatch, and a world clock.

Awqati provides alerts for prayer times, Dhikr, and Wird, with customizable sounds and alerts and configurable quiet hours. It supports Arabic and English and makes its features available through accessible interfaces and keyboard shortcuts.

# System Requirements and Installation

## System requirements

Awqati requires NVDA 2026.1 or later and has been tested up to version 2026.3.1.

The core features work offline, while weather, Wikipedia, prayer time verification, and data updates require an internet connection when retrieving information. Automatic location detection relies on the Windows location service.

## Installing, updating, and removing the add-on

You can install and update Awqati from the NVDA Add-on Store or by using the .nvda-addon installation package available in the project's GitHub repository.

You must restart NVDA to complete installation or an update. You do not need to remove the previous version before installing a newer one.

To disable or remove the add-on, open the NVDA Add-on Store, go to the installed add-ons, select Awqati, and choose the required action.

## Preserving settings when updating

Awqati retains its settings and time tool data during updates, including the location, calendars, alerts, alarms, and timers.

The add-on's data is stored in the awqati folder inside the NVDA configuration folder. It is advisable to back up this folder before major updates.

# Getting Started with Awqati

## First launch

When you run Awqati for the first time, a dialog appears for selecting the location used to calculate prayer times and related information. You can cancel the dialog and set your location later in the add-on's settings.

Once you have set your location, the features that depend on it are ready to use, and you can customize the remaining settings as needed. The weather service is disabled by default until you enable it.

## Setting your location

The add-on offers three ways to set your location:

- **Choose from the list:** Select a country and city from the built-in location database, with support for searching by typing.
- **Automatic detection:** Use the Windows location service, then accept or reject the result displayed.
- **Custom location:** Enter the location's name, coordinates, and time zone.

Prayer times, astronomical information, Qibla direction, and Ghurubi time depend on the selected location, so you should make sure it is correct.

When you use a custom location with the prayer time calculation method set to "Automatic by country", the add-on asks you to choose a specific calculation method. You can change your location later in the settings.

## Opening the add-on's settings

Press NVDA+Alt+A to open Awqati's settings. You can open the Weather settings page directly with NVDA+Alt+W.

The settings dialog lets you configure services, alerts, and general options, and either save or cancel your changes.

## Understanding the settings pages

Awqati's settings dialog has a fixed section and a section whose options change according to the selected page.

The fixed section contains location settings, overall alert controls, quiet hours, Qibla direction, copying diagnostic information, and checking for data updates.

The variable section contains five pages:

- **Prayer times:** Settings for calculation methods, time adjustments, alerts, and Iqama.
- **Clock:** Settings for Zawali and Ghurubi time, speech formats, and clock alerts, as well as access to the time tools.
- **Calendar:** Settings for calendars and date formats, date converters, and daily, astronomical, and traditional calendar information.
- **Weather:** Settings for weather queries, detail levels, units of measurement, and report display options.
- **Dhikr alerts:** Settings for morning and evening Dhikr, the Friday hour, daily Wird, and recurring Dhikr reminders.

The Prayer times page is selected by default when you open the settings. Selecting a page displays its options without the options from the other pages.

## Using keyboard shortcuts

Awqati provides shortcuts for querying information and opening and controlling its tools without having to open the settings each time. You can review and customize these shortcuts in NVDA's Input Gestures dialog, under the Awqati category. The assigned shortcuts and their functions are listed in the Keyboard Shortcuts section of this guide.

## Commands with multiple presses

Some Awqati shortcuts use consecutive presses for different functions, within the timeout specified in NVDA. The function of each press is listed in the Keyboard Shortcuts section.

## Saving settings and applying changes

OK saves your changes and closes the settings, while Apply saves them without closing the dialog. Cancel discards unsaved changes. Changes to the time tools are saved immediately and independently.

# Location Settings

## Choosing a country and city

Awqati includes a database of locations around the world. You can select a country and then a city, with support for searching by typing in both lists. The selected location is used to calculate prayer times and related information.

If your location is not listed, you can enter it as a custom location.

## Automatic location detection

The add-on can determine your location using the Windows location service. When you request automatic detection, it displays the detected location for you to accept or reject, without automatically changing your saved location.

The accuracy of the result depends on the information supplied by the Windows location service, so it is advisable to check it before accepting it.

## Entering a custom location

You can add a location that is not in the database by entering its name, coordinates, and time zone.

If the calculation method is set to "Automatic by country", the add-on asks you to select an explicit calculation method when you save a custom location. It does not choose a method for you, and canceling the operation leaves your previous settings unchanged.

## Coordinates and time zone

The add-on uses latitude and longitude to identify the geographical location and the time zone to calculate and display times in local time.

When entering a custom location, make sure the coordinates are correct and select the appropriate time zone, taking daylight saving time into account in regions that observe it.

## Changing the selected location

You can change the location in the general section of Awqati's settings using any of the available location selection methods. Once you accept the new location, its data is used for location-dependent calculations. Other settings are retained unless changing the location requires an explicit adjustment, such as choosing a prayer time calculation method for a custom location.

## How location affects prayer times and astronomical information

Prayer times, Ghurubi time, Qibla direction, and daily astronomical information depend on the coordinates and time zone of the selected location. The prayer time calculation method is determined by the prayer time settings, and results may differ between methods even for the same location. You should therefore check both the location and calculation method if you notice differences in prayer times or astronomical information.

# Prayer Times

## About the prayer time service

Awqati calculates prayer times for the selected location using the chosen calculation method. It provides customizable alerts for the five daily prayers, as well as sunrise, the midpoint of the night, and the start of the last third of the night.

Times are calculated locally without an internet connection, with the option to verify them against an external source on request.

## Querying prayer times

NVDA+F11 provides three functions through consecutive presses:

- One press: Details of the current time period.
- Two presses: The previous time period.
- Three presses: Today's prayer times.

The information provided depends on the location and settings selected in the add-on.

## Displaying today's prayer times in a text window

NVDA+Alt+P opens a window containing today's full prayer times, which you can review and copy.

You can also open the window using the "Open daily prayer times window" button in the prayer time settings.

## Previous, next, and current prayers

The add-on identifies the previous and next prayers according to local time and takes the calculated Iqama times into account when determining the current prayer.

A prayer remains classified as current for the specified period after Iqama, then moves to its next state according to the prayer time system.

## The midpoint and last third of the night

The add-on calculates the midpoint of the night and the start of its last third from the interval between sunset and Fajr the following day, rather than by dividing the hours of the civil day.

These times are included in the prayer time information, and you can customize their associated alerts.

## Prayer time calculation method

The "Prayer calculation method" option lets you choose an available calculation method or use "Automatic by country" to select the appropriate method for the chosen country.

Results may differ between calculation methods, particularly for Fajr and Isha. You are advised to choose the method approved by the relevant authority in your country.

When you use a custom location with the automatic option, the add-on asks you to select an explicit calculation method.

## Calculating Asr time

Two options are available for calculating the start of Asr:

- **Standard:** The method used by the Shafi'i, Maliki, and Hanbali schools.
- **Hanafi:** The method used by the Hanafi school.

This choice affects the calculation of Asr only, without changing the other times.

## High latitude adjustment

This setting determines how Fajr and Isha are calculated in areas where twilight is prolonged or standard calculations are not possible.

The Automatic option applies an appropriate adjustment for the circumstances. You can also choose another available method as needed.

## Verifying prayer times online

The "Verify today's prayer times online" button lets you compare the times calculated by the add-on with those from an external provider.

The add-on displays the differences without automatically changing its calculated times or settings. This feature requires an internet connection.

## Adjusting prayer times

The "Time adjustment in minutes" option lets you move a calculated time earlier or later by a specified number of minutes.

The default value is zero, and you can customize the adjustment for each time separately. It is best to change it only when you need to match locally approved times.

## Iqama settings

Iqama settings are available for the five daily prayers. Iqama times are calculated by adding the specified interval to the start of each prayer time.

The default intervals between Adhan and Iqama are:

- Fajr: 25 minutes.
- Dhuhr: 20 minutes.
- Asr: 20 minutes.
- Maghrib: 10 minutes.
- Isha: 20 minutes.

You can adjust the interval for each prayer independently. Setting it to zero disables the Iqama system for that prayer; the period during which it is considered current then begins at the start of its prayer time.

## Pre-Iqama alert

This setting specifies how many minutes before the calculated Iqama time the alert occurs.

The default value is five minutes. You can change it or disable the alert by choosing the appropriate action.

## How long a prayer remains current

The "Keep prayer current after Iqama, minutes" option specifies how long a prayer remains classified as current after its calculated Iqama time.

The default value is 20 minutes, adjustable from zero to 180 minutes. If Iqama is disabled for a particular prayer, this duration is measured from the start of its prayer time.

## Enabling and disabling prayer time alerts

The "Enable prayer time alerts" option controls all prayer time alerts, including alerts before the time, at its start, for Iqama, and after the time.

Disabling it stops these alerts without deleting their settings. They resume when you enable it again, provided that the master switch for automatic alerts is enabled.

## Alerts before a time begins

You can set an alert a specified number of minutes before each time begins. The default is ten minutes.

The specified interval also serves as the waiting window before the time begins; there is no separate waiting window. Setting it to zero removes this window.

## Alerts when a time begins

This setting specifies the action performed when the calculated time begins: speech, playing an audio file, or both.

You can set the action for each time independently, or choose Silent to prevent an alert when it begins.

## Alerts after a time begins

Separate alerts after the time are available for sunrise, the midpoint of the night, and the start of the last third of the night.

You can specify the interval between the calculated time and the alert and choose the action used for it.

## Customizing alert actions for each time

Alerts are configured through the "Time to configure" list, which includes Fajr, sunrise, Dhuhr, Asr, Maghrib, Isha, the midpoint of the night, and the last third of the night.

Selecting a time displays its specific settings, including adjustments and the alerts available for it.

The following alert actions are available:

- Silent.
- Speech only.
- Sound file only.
- Sound file and speech.<br>When you choose an action that includes an audio file, options appear for selecting, previewing, and removing the file.
- You can use a file containing the Adhan, the Iqama, or any other sound you prefer.

Some settings depend on the selected time: the five daily prayers include Iqama settings, while sunrise, the midpoint of the night, and the last third have separate alerts after the time.

# Clocks and Timekeeping

## Querying the time

Awqati provides two clocks: Zawali, the conventional clock, and Ghurubi, which uses sunset as the starting point for counting the hours of the night and day.

NVDA+F12 provides time, date, and day information according to the number of presses:

- One press: The current time.
- Two presses: The date in the primary calendar.
- Three presses: Day information.

The clock settings let you customize time announcements and automatic alerts for each clock.

## Zawali time

Zawali time is the conventional time system in which the day begins at midnight. It uses the computer's local clock.

You can customize its speech format, hour system, and the details announced when you query it.

## Ghurubi time

Ghurubi time is a traditional system that counts hours from sunset. Nighttime hours begin at sunset and are followed by daytime hours until the next sunset.

The add-on uses your saved location to calculate this time, so its hours vary by location and season.

Press NVDA+G once to query Ghurubi time. Two presses provide the Qibla direction, and three presses announce the selected location.

## Hour systems

The "Hour system" option lets you choose between 12-hour and 24-hour time according to your preferred display and speech format.

Zawali and Ghurubi clock settings are configured independently using "Choose clock settings" in the clock settings.

## Time speech formats

The add-on lets you choose a speech format and the level of detail announced for the time. The "Speech representation" option also lets you choose whether the time is read in words or numbers.

These options apply to the selected clock without changing the other clock's settings.

## Announcing seconds

This option determines whether time announcements include seconds or only hours and minutes.

## Announcing "zero minutes"

This option determines whether the add-on says "zero minutes" on the hour or announces the hour without mentioning minutes.

## Previewing speech

The "Preview speech" button lets you hear the time using the selected settings so you can check the format, representation, and details before saving your changes.

## Automatic clock alerts

You can enable or disable automatic clock alerts and select one or more of the following points:

- Quarter past the hour.
- Half past the hour.
- Quarter to the hour.
- On the hour.

Disabling clock alerts stops them while retaining their settings. The master switch for automatic alerts in Awqati must be enabled for them to work.

## Customizing clock alert actions

You can choose a clock alert action from the following options:

- Speech only.
- Sound file only.
- Sound file and speech.

The add-on includes a default audio file that you can replace with a custom file, with options to preview or remove it.

The Clock page also provides other time management tools: alarms, countdown timers, a stopwatch, and a world clock. Instructions and settings for these tools appear in separate sections later in this guide.

# Calendars and Dates

## Supported calendars

Awqati supports five calendars, with independently customizable date display and speech formats for each:

- Gregorian calendar.
- Lunar Hijri calendar.
- Saudi Solar Hijri calendar.
- Afghan Solar Hijri calendar.
- Persian Solar Hijri calendar.

Only Gregorian and Lunar Hijri can be selected as the primary calendar. The three solar calendars are available for separate queries.

## Querying the date

Press NVDA+F12 twice to query the date in the selected primary calendar.

Separate shortcuts are available for the other calendars:

- NVDA+H: Once for the Lunar Hijri date, twice for the Saudi Solar Hijri date, and three times for the traditional Arabian calendar summary.
- NVDA+Shift+H: Once for the Afghan Solar Hijri date and twice for the Persian Solar Hijri date.

## Choosing the primary calendar

The "Primary calendar" option determines the calendar used for general date queries. You can choose Lunar Hijri or Gregorian.

Lunar Hijri is the default. Changing the primary calendar does not affect your ability to use the other calendars.

## Customizing date formats

On the Calendar page, choose the calendar to configure, then select a date display and speech format from the available options, including dual, full, medium, and short formats.

Each calendar's settings are saved independently. Changing its format does not affect the other calendars.

## Adjusting the Lunar Hijri date

This option lets you move the Lunar Hijri date forward or backward by a number of days to match the locally adopted date.

The default value is zero, meaning no adjustment. This setting affects only the Lunar Hijri date and does not apply to date converter results.

## Previewing date speech

The "Preview speech" button lets you hear the date in the selected calendar and speech format before saving your changes.

## Simple date converter

The simple date converter provides direct conversion between Gregorian and Lunar Hijri dates using the built-in Umm al-Qura table.

To open it, go to the Calendar page in Awqati's settings and choose "Open date converter".

Select the conversion direction, enter the day, month, and year, and choose Convert. The Today button enters the current date for the selected location, while "Advanced..." opens the advanced converter.

## Advanced date converter

The advanced converter converts dates between the Lunar Hijri, Gregorian, and Julian calendars, with a choice of conversion method when applicable.

Open it using the "Advanced conversion..." button on the Calendar page, or access it from the simple converter.

Select the source and target calendars and the conversion method, then enter the required date. Method selection is disabled when neither side of the conversion is Hijri.

## Conversion methods and their limits

The advanced converter provides two Hijri conversion methods:

- **Umm al-Qura:** Uses the built-in table within the range of dates it covers.
- **Historical arithmetic IIc:** Uses historical calendar arithmetic and does not establish crescent visibility.

The conversion engine contains additional arithmetic methods internally for testing and comparison, but the interface provides the two methods listed above.

The add-on displays a message if you enter a date outside the supported range. Conversion is not affected by your personal Hijri date adjustment and does not change saved calendar settings.

## Copying and reversing a conversion

The conversion result appears in a window containing the original date, the converted date, and the reference used.

"Copy result" copies the resulting date to the clipboard. "Reverse conversion" swaps the source and target calendars and updates the converter fields when you return to it.

An Open date converter command is also available under the Awqati category in Input Gestures, without a default shortcut. Once you assign a shortcut, one press opens the simple converter and two consecutive presses open the advanced converter.

# Astronomical Information

## About the daily astronomical synopsis

Awqati provides a daily astronomical synopsis with information about the Sun, Moon, seasons, and lengths of day and night, based on the selected location, date, and time.

The information is calculated locally and presented as connected text covering the main astronomical data, without requiring an internet connection.

The traditional Arabian calendar remains a separate section that can be included in day information when its option is enabled.

## Accessing astronomical information

You can query astronomical information using NVDA+Ctrl+H:

- One press: Speak astronomical information.
- Two presses: Speak traditional Arabian calendar information.
- Three presses: Open the day information window.

Three presses of NVDA+F12 also provide day information, according to the settings for including traditional calendar information.

You can also open the window using "Open daily information window" on the Calendar page. The window lets you read, review, and copy the information.

## Astronomical seasons, solstices, and equinoxes

The synopsis identifies the current astronomical season, the current day's position within it, and the time remaining until it ends, along with the start of the next season.

Seasonal transitions are based on the spring and autumn equinoxes and summer and winter solstices as determined by astronomical calculations, rather than climatic or traditional divisions of the seasons.

## Sunrise and sunset

The add-on provides sunrise and sunset times in local time for the selected location.

These times are also used to calculate the lengths of day and night and for some features related to Ghurubi time.

## Lengths of day and night and how they change

The synopsis describes the lengths of day and night and the change in day length, with information on how the day lengthens or shortens over the annual cycle.

It also includes information about the longest day and longest night and their actual dates for the selected location.

## Solar meridian transit and altitude

The add-on provides the time when the Sun crosses the local meridian and its altitude above the horizon at transit.

Meridian transit is the moment when the Sun reaches the local meridian; it does not necessarily occur at twelve noon in civil time.

## Earth–Sun distance

The synopsis includes the approximate current distance between the centers of the Earth and Sun, which varies over the year as the Earth moves in its orbit.

## Moon phases, age, and illumination

The synopsis provides the current lunar phase, the Moon's approximate age, and the illuminated fraction of its disc as seen from Earth.

This information changes continuously throughout the lunar month and cannot, on its own, establish crescent visibility.

## Moonrise and moonset

The add-on provides moonrise and moonset times in local time, respecting their actual chronological order.

The Moon may not rise or set during a particular civil day. In that case, the add-on indicates that the event does not occur instead of displaying a default time.

## Lunar meridian transit and maximum altitude

The synopsis provides the time when the Moon crosses the local meridian and its altitude at transit, as well as the time when it reaches its actual maximum altitude above the horizon.

The two events are calculated independently, as the time of maximum altitude may differ from the time of meridian transit.

## Earth–Moon distance

The add-on provides the approximate current distance between the centers of the Earth and Moon, which varies throughout the month as the Moon moves in its orbit.

## Upcoming lunar phases

The synopsis includes the upcoming times of the main lunar phases, in chronological order:

- New moon.
- First quarter.
- Full moon.
- Last quarter.

Times are displayed in the selected location's time zone.

## Limits and accuracy of astronomical calculations

Astronomical information is based on computational models. The accuracy of some results may be affected by the limitations of those models and the inputs used.

The add-on identifies cases in which a particular item cannot be calculated and displays technical notes when needed, including notes about the astronomical time difference (ΔT).

Lunar phase times and calculated data do not establish a crescent sighting for religious purposes.

# The Traditional Arabian Calendar

## About the traditional Arabian calendar

Awqati provides separate information about the traditional Arabian calendar, including the Suhail year, Talaa periods, and the seasons and seasonal periods known in Arabian heritage.

This information is presented according to the traditional calendar adopted by the add-on, as historical and cultural knowledge distinct from modern astronomical calculations.

## Enabling and disabling traditional calendar information

You can include traditional Arabian calendar information in day information using "Include Arabian calendar information in day information" in the calendar settings.

When this option is disabled, astronomical information remains available without the traditional section. You can also query traditional calendar information separately.

## The Suhail year

The add-on provides the current day of the Suhail year according to the traditional Arabian calendar, allowing you to follow the progress of the year and the position of the current date within it.

This division differs from the start of the Gregorian and Hijri years and is not intended to replace either calendar.

## Talaa periods

The add-on identifies the current Talaa period within the sequence adopted by the Arabian calendar, along with its associated timing and traditional information.

In Arabian tradition, Talaa periods divide the year into intervals associated with seasons and customary changes in nature.

## Traditional seasons and seasonal periods

Traditional calendar information includes the names of the seasons and seasonal periods known in the Arabian calendar and the current day's position within them.

These divisions reflect traditional Arabian experience of the year's seasons and conditions. Their boundaries may differ from the dates of the astronomical seasons.

## Displaying traditional calendar information within day information

When the option to include the Arabian calendar is enabled, the traditional section appears separately within day information, after the astronomical information.

You can query it directly by pressing NVDA+Ctrl+H twice, or press NVDA+H three times for the day's Arabian calendar summary.

## The relationship between the traditional calendar and astronomical information

Awqati brings together modern astronomical information and the traditional Arabian calendar while keeping them clearly distinct.

Astronomical information is based on calculations of the movements of the Earth, Sun, and Moon, while the traditional calendar uses inherited divisions of time and seasons.

The starts of seasons and seasonal periods may therefore differ between the two systems without either being incorrect: each has its own basis and way of dividing the year.

# Weather

## About the weather service

Awqati provides current weather conditions and forecasts for today and the coming days, as well as hourly forecasts. The service uses the location and time zone saved in the add-on, without requiring you to select another location.

The service is optional and disabled by default. It requires an internet connection to retrieve data, but no account or private key.

## Enabling and disabling the service

To open the weather settings directly, press NVDA+Alt+W, select "Enable weather service", and save your changes.

To disable the service, clear the same option. Updates then stop, while your settings are retained for use when you enable it again.

## Current weather conditions

Press NVDA+W once to query the current weather conditions.

The brief report gives the city name, a description of the weather, and the current temperature, along with today's high and low temperatures.

You can obtain additional information, such as feels-like temperature, humidity, wind, and atmospheric pressure, by selecting the detailed report.

## Today's forecast

Press NVDA+W twice in succession for today's forecast.

The report includes the expected weather, high and low temperatures, and the highest precipitation probability during the available hours. Depending on the selected settings, it can also include additional information and hourly periods.

## Forecast for the coming days

Press NVDA+W three times in succession to query the forecast for the coming days.

You can set the forecast duration to between two and six days, starting tomorrow. The default is two days.

The report provides each day's expected weather, high and low temperatures, and precipitation probability, with additional details when the detailed level is selected.

## Hourly forecasts

The add-on can include forecasts for the coming hours in today's detailed report, with a choice of three time horizons:

- Three hours.
- Six hours, the default.
- Twelve hours.

Readings are distributed across the selected horizon at appropriate intervals. They are forecasts for specific times, rather than averages for the intervals between them.

You can disable hourly periods in the settings. With the brief report selected, the add-on only mentions significant expected changes instead of listing hourly readings.

## Detail levels

The add-on provides two report levels:

- **Brief:** Presents the essential weather information without additional details.
- **Detailed:** Includes the additional information you select, such as humidity, wind, precipitation, and hourly data.

Brief is the default. The selected level applies to reports regardless of how many times you press the query shortcut.

## Customizing weather report information

The "Customize weather information" button lets you choose the additional data included in detailed reports, with separate settings for current conditions, today's forecast, and the coming days.

Options for current conditions include feels-like temperature, humidity, wind gusts, atmospheric pressure, visibility, cloud cover, precipitation, UV index, and the US Air Quality Index.

Daily forecast options include precipitation amount, maximum wind speed and gusts, and maximum UV index.

Disabling these items does not remove the report's fixed essential information.

## Units of measurement

Awqati supports three weather unit systems:

- **Metric:** The default, using Celsius, kilometers per hour, hectopascals, kilometers, and millimeters.
- **Imperial:** Uses Fahrenheit, miles per hour, inches of mercury, miles, and inches.
- **Custom:** Lets you choose a separate unit for each type of measurement.

Additional available units include kelvin, meters per second, knots, millibars, and millimeters of mercury.

The add-on retains your custom units when you switch systems and converts values locally without requiring a new connection.

## Displaying information in a text window and copying it

After a successful weather query, you can open the last successful report using "Open weather information in a text window".

The window displays the saved report with its type, detail level, units, query time, and data source. You can read and copy the text using standard editing commands or choose "Copy report".

Opening the window does not retrieve new data, and a later failed query does not replace the last successful report. If the window is open when you request a new report, close it and reopen it to display the latest report.

The command for opening the window is available under the Awqati category in Input Gestures, without a default shortcut.

## Including a weather summary in day information

The "Include weather conditions in day information" option adds a summary of current weather conditions to day information after the astronomical and traditional calendar information.

The option is disabled by default. It uses available cached weather data without delaying the reading of day information while waiting for a connection.

If valid data is unavailable, the usual day information is provided and a silent retrieval begins so the result can be used for the next query.

## Updating weather information

You can set automatic updates to every 15, 30, or 60 minutes. The default is 30 minutes. Automatic updates run without a spoken announcement.

To update information manually, use "Update now". This command uses the saved settings, so you should apply any changes before requesting an update.

The add-on uses a cache to reduce repeated connections. If it cannot refresh the data, it may use saved information less than two hours old, with a warning that it may be out of date.

Air quality data has a separate cache lifetime of one hour.

## Data source and privacy

The weather service uses Open-Meteo. When the US Air Quality Index is enabled, air quality data is retrieved from CAMS through the same service.

When you use the service, your location coordinates and time zone are sent to the provider over HTTPS, and your IP address is visible to it. Prayer settings and personal account data are not sent.

Weather information is cached in memory and removed when NVDA exits. Text reports include source and licensing information, which is omitted from spoken reports.

Official data source website: [https://open-meteo.com/](https://open-meteo.com/)

Forecasts are based on weather models and are not a substitute for official warnings from the relevant meteorological authorities.

## When information cannot be retrieved

If weather data cannot be retrieved, the add-on tries to use saved data that is still usable, with a warning when it displays outdated information.

If no suitable data is available, it announces a message explaining that the information could not be retrieved, without displaying default values or data for a previous location.

Failure to retrieve air quality data does not prevent the remaining available weather information from being displayed.

If the problem persists, check your internet connection, the selected location, and whether the weather service is enabled. The failure may be due to a temporary outage at the data provider or the service's usage limits being reached.

# On This Day

## About the service and its information source

On This Day lets you browse historical events, births, deaths, holidays, and observances associated with today's date, using information from Wikipedia.

The service uses NVDA's language, Arabic or English, and presents information in its original language without machine translation. It uses the computer's local date and requires internet access to retrieve information that has not been saved.

## Historical events

This section presents notable events that occurred on this date over the years, giving the year of each event and its description as published on Wikipedia.

## Births

This section presents people born on this date, with their birth year and the available biographical information for each person.

## Deaths

This section presents people who died on this date, with their year of death and the available biographical information about them.

## Holidays and observances

This section includes holidays, observances, and commemorative days associated with the current date.

The add-on retains Wikipedia's original divisions of observances and displays them in groups when available.

## Using the multiple-press shortcut

Use NVDA+Windows+F12 to access the service's sections:

- One press: Historical events.
- Two presses: Births.
- Three presses: Deaths.
- Four presses: Holidays and observances.

Presses must be consecutive and within the timeout specified in NVDA. You can customize the shortcut under the Awqati category in Input Gestures.

## Direct narration

Direct narration is the service's default mode. The add-on reads all items in the requested section without speaking link addresses.

You can stop narration with Control, or pause and resume it with Shift, depending on your NVDA settings and speech synthesizer.

Choosing another section stops the previous narration and moves to the new information.

## Displaying information on a web page

You can replace direct narration with information displayed on a local web page that opens in your default browser.

To enable this mode, open Awqati's settings, select the Calendar page, and enable "Show On This Day information in a web page instead of speaking it".

Your choice is saved in the add-on's settings. To return to direct narration, clear the same option.

The page displays the section title and date, a summary of the number of items, and then the information arranged as separate items.

## Navigating the page and opening Wikipedia links

The service's pages support standard navigation using NVDA's browse mode, including navigation by headings, lists, and links.

Each event or person appears as a separate item, with links that open the related Wikipedia articles directly.

You can select and copy information or print it using standard browser commands.

## Local information storage

The add-on retains the day's information after retrieving it, allowing you to review it offline during the same day.

Display pages are saved in the on_this_day_pages folder within Awqati's data in the NVDA configuration folder.

The saved page is updated when you open it later, and its title shows the information's date. Data from a previous day is not presented as information for the current day.

## Errors and unavailable information

Some Wikipedia sections may be unavailable in the selected language, or retrieval may fail because of the connection or changes to the source page's structure.

When a section is missing, the add-on displays "Information is unavailable in the selected language.", with separate messages for connection and content extraction errors.

The add-on does not replace missing information with content from another language, and it avoids presenting incomplete data or empty pages as complete results.

If information cannot be retrieved, you can try again later or visit Wikipedia directly.

# Alarms

## Opening the alarm manager

Awqati lets you create recurring personal alarms, with a customizable time, active days, sound, and snooze settings for each alarm.

To open the alarm manager, press NVDA+Alt+F8, or go to Time tools on the Clock page in the add-on's settings and choose Alarms.

Changes to alarms are saved immediately, without having to save the clock settings.

## Creating an alarm

Choose to add a new alarm, then enter its name and time and select the repeat days and alert action.

You can create multiple alarms with independent settings. Alarms are saved for use when NVDA runs again.

## Setting the alarm time and repeat days

Alarm times use the 24-hour system, with hours from 0 to 23 and minutes from 0 to 59.

You must select at least one repeat day. You can select particular days of the week or all seven days for a daily alarm.

The add-on does not currently provide one-time alarms; all alarms use weekly recurrence.

## Customizing alarm sounds

You can choose an independent action for each alarm: speech, sound, or both, with the option to use a custom WAV audio file.

The add-on also lets you set the ringing duration, snooze interval, and number of snooze repeats.

You can also specify whether the alarm respects quiet hours. By default, it bypasses them.

## Editing and deleting alarms

You can edit an alarm's time, name, repeat days, sound settings, and snooze settings in the alarm manager.

You can also delete alarms you no longer need. Editing or deleting an alarm cancels any pending snooze for it.

## Enabling and disabling alarms

You can disable an individual alarm without deleting it, retaining all its settings so you can enable it again later.

Alarms are subject to Awqati's master switch for automatic alerts, even when individually enabled.

## When an alarm rings

Alarms use the Windows clock and time zone, rather than the location selected for calculating prayer times.

When several alerts coincide, the add-on manages them according to its priority system. Prayer alerts may interrupt a ringing alarm.

Alarms do not work while NVDA is not running or the computer is turned off. The add-on allows a limited grace period for handling delayed alerts.

## Snoozing and stopping an alarm

You can control the active alarm using these shortcuts:

- NVDA+Shift+F8: Snooze the alarm for the configured snooze duration.
- NVDA+F8 three times: Stop the currently ringing alarm.

Stopping ends the current ringing cycle without snoozing it. Snoozing causes the alert to sound again after the specified interval.

You can query the next alarm by pressing NVDA+F8 once, or the number of enabled alarms by pressing it twice.

# Timers

## Opening the timer manager

Awqati provides multiple countdown timers that can run independently.

To open the timer manager, press NVDA+Alt+Y, or choose Timers from the Time tools list on the Clock page.

## Creating a timer and setting its duration

Choose to create a new timer, then enter an optional name and set the duration in hours, minutes, and seconds.

The maximum duration is 999 hours, 59 minutes, and 59 seconds. You cannot create a timer with a duration of zero.

You can save timers for later reuse without entering their details again.

## Running multiple timers

You can run several timers at the same time, each counting down independently.

Press NVDA+Y once to query the selected timer and its remaining time, or twice for its state and the number of timers.

To move between timers:

- NVDA+Windows+Y: Next timer.
- NVDA+Windows+Shift+Y: Previous timer.

Navigation wraps around in the order of the timers in the list and does not affect their operation.

## Pausing and resuming a timer

NVDA+Shift+Y starts, pauses, or resumes the selected timer, depending on its state.

The countdown continues while the computer is asleep and is not affected by changes to the Windows clock during the session.

## Restarting a timer

You can reset a timer to its original duration using NVDA+Ctrl+Shift+Y.

Restarting requires confirmation, with No selected by default to prevent accidental resets.

## Customizing timer sounds

You can set an independent alert action for each timer using speech, sound, or both, with the option to select and preview a custom WAV file.

Options are available to play the alert once or repeat it at a specified interval.

To silence a completed timer, press NVDA+Ctrl+Y. This ends its ringing and repeats without changing the timer's completed state.

## Enabling clock ticking

The "Play clock ticks" option enables a ticking sound while the selected timer is running. It is disabled by default.

Ticking is limited to the selected timer and is muted during higher-priority alerts or sound previews, without affecting other timers.

## Managing and deleting timers

You can edit or delete saved timers or cancel their active cycles. You must cancel a timer's current cycle before editing it.

Deletion requires confirmation, with No selected by default.

The add-on retains saved timers and restores running timers after NVDA restarts, taking elapsed time into account. Disabling automatic alerts does not stop the countdown; it only prevents the completion alert.

# Stopwatch

## Opening the stopwatch

Awqati provides a stopwatch for measuring elapsed time, recording laps, and reviewing their results.

To open its window, press NVDA+Ctrl+J, or choose Stopwatch from the Time tools list on the Clock page.

## Starting and stopping timing

NVDA+J controls timing according to the stopwatch's state.

You can query elapsed time by pressing NVDA+Windows+J once, or the stopwatch's state and number of recorded laps by pressing it twice.

## Pausing and resuming timing

NVDA+J lets you pause timing and then resume it without losing the recorded time.

Timing continues while the computer is asleep and is not affected by changes to the civil clock.

After NVDA restarts, the stopwatch is restored in a paused state at its last saved value.

## Recording laps

You can record consecutive laps while timing using NVDA+Shift+J.

The add-on retains each lap's time and the total elapsed time without stopping timing when a lap is recorded.

## Reviewing laps

The stopwatch window displays a list of recorded laps, including each lap's number, duration, and total time.

Press NVDA+Windows+Shift+J once to query the current lap's duration, or twice for the duration of the last recorded lap.

Query commands do not affect timing or results.

## Copying results

The stopwatch window lets you copy timing results and recorded laps as text to keep them or use them in another application.

## Resetting the stopwatch

To reset the stopwatch to zero, pause timing and press NVDA+Ctrl+Shift+J.

This requires confirmation, with No selected by default. You cannot reset the stopwatch while timing is running.

You can customize action confirmations to use tones, speech, or both, or disable confirmation sounds.

# World Clock

## Opening the world clock

Awqati lets you track the time in multiple cities around the world and keep a personal list of favorite cities.

To access it, open the add-on's settings, go to the Clock page, and choose World clock from the Time tools list.

## Searching for cities

The "Add city" option lets you search for cities in Arabic or English and select the required city from the database.

## Adding cities to favorites

After finding a city, you can add it to your favorite cities list for direct access.

The list and its order are saved independently of the location settings used to calculate prayer times.

## Displaying city times

The world clock displays each city's local time according to its time zone.

NVDA+Ctrl+F12 provides quick access to the first three cities in the list:

- One press: The first city's time.
- Two presses: The second city's time.
- Three presses: The third city's time.

The query order follows the order of cities in the list. Querying does not change the selected city.

## Reordering favorite cities

You can reorder favorite cities using the commands available in the world clock interface.

The new order determines which cities are announced using the multiple-press query shortcut.

## Customizing city names

You can customize a city or country name using "Edit name" in the context menu.

Arabic and English names are saved independently, and you can restore the original names when needed.

Changing a name does not affect the city's time zone or how its time is calculated.

## Removing cities from favorites

You can remove any city from the favorites list using the delete command after confirming the operation.

Removing a city does not affect other location data or the location selected for calculating prayer times.

## Time zones and daylight saving time

The world clock calculates city times using Coordinated Universal Time (UTC) and time zone rules, including transitions into and out of daylight saving time.

The world clock uses its own time zone data and provides an option to update it manually or automatically.

Automatic updates are enabled by default, with a weekly check. You can disable them while keeping manual updates available.

Data updates take effect without restarting NVDA, while preserving the city list, its order, and custom names.

# Qibla Direction

## About the Qibla direction service

Awqati provides Qibla direction information based on the location selected in the add-on, without requiring an internet connection.

The information is given in descriptive and numerical form to help you determine the direction toward Makkah.

## Displaying the Qibla direction

You can query the Qibla direction by pressing NVDA+G twice or using "Show Qibla direction" in the add-on's settings.

The result includes the general Qibla direction, the amount of deviation, and the precise angle measured from true north.

## How the Qibla direction depends on the selected location

The Qibla direction is calculated from the coordinates of the location saved in Awqati, and the result changes when you change the location.

The add-on cannot determine the direction the computer or user is facing. To use the result in practice, you therefore need to know the direction of true north at your location.

This service is a guide, rather than a substitute for checking the Qibla direction on site.

# Dhikr and Wird

## Enabling Dhikr alerts

Awqati provides five independent reminder features for Dhikr and Wird: morning Dhikr, evening Dhikr, the Friday hour, daily Wird, and recurring Dhikr.

These features are disabled by default. You can enable each independently on the Dhikr alerts page.

The "Enable Dhikr alerts" option controls all alerts in this section without deleting their settings when disabled.

## Morning Dhikr

You can schedule the morning Dhikr reminder relative to one of these times:

- After Fajr.
- Before sunrise.
- After sunrise.

Specify the number of minutes relative to the selected time. The default is an alert fifteen minutes before sunrise.

## Evening Dhikr

You can schedule the evening Dhikr reminder relative to one of these times:

- After Asr.
- Before Maghrib.
- After Maghrib.

The default is an alert fifteen minutes before Maghrib. You can change the reference time and interval as needed.

## Friday hour reminder

This reminder operates on Fridays and can be set to a specified number of minutes after Asr or before Maghrib.

The default is an alert sixty minutes before Maghrib.

The reminder time depends on the prayer times calculated for the selected location.

## Daily Wird alert

This option lets you set a fixed daily time for a Wird reminder, with customizable alert text.

The default time is ten in the evening. You can change it in the daily Wird settings.

## Customizing alert actions

You can set an independent action for morning Dhikr, evening Dhikr, the Friday hour, and daily Wird from these options:

- Speech only.
- Sound file only.
- Sound file and speech.

Each feature's choices are saved independently. Changing one alert's action does not affect the other alerts.

## Default and custom sounds

The add-on provides alert sounds, with the option to choose a custom audio file.

When you choose an action that plays an audio file, options appear for selecting, previewing, and removing the file.

## Recurring Dhikr reminders

The "Enable recurring Dhikr reminder" option activates successive reminders for a set of Dhikr, at an interval you specify.

You can enable or disable each Dhikr independently and assign it its own action, either speech or an audio file.

The first reminder occurs after the specified interval has elapsed, rather than immediately when the feature is enabled.

You can toggle recurring Dhikr on and off using NVDA+Shift+F11.

## Recurring Dhikr order

The add-on moves through the enabled Dhikr in their cycle order, skipping disabled Dhikr without issuing alerts for them.

Recurring reminders continue to cycle through the enabled Dhikr while the feature is active and alerts are allowed.

## Setting the reminder interval

This setting specifies the interval between recurring reminders.

The default is sixty minutes. You can change it in the recurring Dhikr settings.

The same interval is used between successive reminders. The first cycle starts counting when you enable the feature.

# Alerts and Quiet Hours

## Enabling and disabling automatic alerts

Awqati includes a master switch for automatic alerts, covering prayer time, clock, Dhikr, and time tool alerts.

You can toggle all alerts on and off using NVDA+Ctrl+Shift+F11 or the general settings.

Disabling alerts does not delete their settings. Alerts enabled in their own sections resume when you turn the master switch back on.

You can query the alert status with NVDA+Alt+F12 and repeat the last spoken alert with NVDA+Shift+F12.

## Speech and audio alerts

The add-on supports spoken alerts, audio file playback, or both, depending on the options available for each feature.

You can customize alert actions independently in the different sections. Some alerts offer a Silent option to stop a particular action without disabling the entire feature.

## Default and custom sounds

Awqati includes default sounds for some alerts, with options to use, preview, or remove custom audio files.

Sound options vary by alert type and are configured in the relevant feature's section.

## Enabling quiet hours

Quiet hours stop automatic alerts during a specified period without changing alert settings or permanently disabling them.

You can enable or disable this feature in the general section of Awqati's settings.

## Setting the start and end of quiet hours

You can set the start and end of the quiet period to suit your sleeping or resting times.

The specified period is applied automatically according to local time. Permitted alerts resume when it ends.

## How quiet hours affect alerts

Not all alerts handle quiet hours in the same way. Settings control whether quiet hours apply to prayer time alerts, while alarms and timers have independent options for respecting them.

Alarms and timers bypass quiet hours by default unless their option to respect them is enabled.

The master switch for automatic alerts takes precedence: disabling it stops the alerts it controls even if they are exempt from quiet hours.

## Managing simultaneous alerts

Awqati manages simultaneous alerts using a priority system to avoid overlapping sounds and spoken messages.

Prayer time alerts have a priority that may interrupt ringing alarms, while simultaneous alarms wait their turn in a queue.

Some secondary sounds, such as timer ticking, may be muted during higher-priority alerts without stopping the countdown or affecting the tools' operation.

# Data Storage and Maintenance

## Saving the add-on's settings

Awqati saves its settings and time tool data in the awqati folder inside the NVDA configuration folder.

Saved data includes the location, calendars, alerts, alarms, timers, and world clock, and is restored when the add-on runs again.

Changes to time tools are saved independently of the OK and Apply buttons in the add-on's settings.

## Preserving data when updating

The add-on retains its settings and data when you update to a newer version, without requiring you to configure the options again.

You are advised to back up the awqati folder before major updates and not to delete it when installing a new version.

Some versions may change the settings structure, and the add-on migrates data when needed. Downgrading to an older version is not recommended without consulting that version's instructions.

## Checking for add-on data updates

The "Check for data updates" button in the general settings checks for newer versions of location, time zone, calculation method, and Arabian calendar data.

The check runs when you request it and requires an internet connection.

The world clock has a separate mechanism for updating time zone data, including a weekly automatic check that you can disable, as well as manual updates.

## Copying diagnostic information

The "Copy diagnostic information" button creates a technical report on the add-on's state, environment, and settings and copies it to the clipboard.

This report is used when reporting a problem or requesting help diagnosing it, excluding sensitive information that is not needed for diagnosis.

## Handling connection errors

The add-on's core features work offline, while some services require a connection to external sources.

If a connection fails, the add-on displays an appropriate message for the service without affecting local features.

Some services may use valid saved data, such as weather and daily Wikipedia information, according to each service's storage policy.

If the problem persists, check your internet connection and try again. You can copy diagnostic information if you need to report the error.

## External data sources and privacy

Awqati uses external sources for some optional features, including:

- **Open-Meteo:** For weather information, forecasts, and air quality.
- **Wikipedia:** For historical events, births, deaths, and observances.
- **An external prayer time provider:** For optional verification of locally calculated prayer times.

When you use the weather service, your location coordinates and time zone are sent to the provider over HTTPS, and your IP address is visible to it.

Local features do not require location data to be sent to these services.

Additional information about sources and the data used is available in each service's section.

# Keyboard Shortcuts

## Customizing shortcuts in NVDA's Input Gestures dialog

You can review and change Awqati's shortcuts, or assign shortcuts to commands without default keys, under the Awqati category in Input Gestures in NVDA's Preferences menu.

Some shortcuts use multiple presses for different functions. Their functions are listed in press order.

NVDA+F12 may conflict with a built-in NVDA command and can be reassigned if needed.

## General shortcuts

- NVDA+Alt+A: Open Awqati's settings.

## Prayer time shortcuts

- NVDA+F11: Once for details of the current time period, twice for the previous time period, and three times for today's prayer times.
- NVDA+Shift+P: Verify today's prayer times online.
- NVDA+Alt+P: Open today's prayer times window.

## Clock and time shortcuts

- NVDA+F12: Once for the current time, twice for the date in the primary calendar, and three times for day information.
- NVDA+G: Once for Ghurubi time, twice for the Qibla direction, and three times for the selected location.

## Calendar and date shortcuts

- NVDA+H: Once for the Lunar Hijri date, twice for the Saudi Solar Hijri date, and three times for the day's Arabian calendar summary.
- NVDA+Shift+H: Once for the Afghan Solar Hijri date and twice for the Persian Solar Hijri date.

## Daily information shortcuts

- NVDA+Ctrl+H: Once for daily astronomical information, twice for traditional Arabian calendar information, and three times to open the day information window.

## Weather shortcuts

- NVDA+Alt+W: Open Awqati's settings with the Weather page selected.
- NVDA+W: Once for current weather conditions, twice for today's forecast, and three times for the coming days' forecast.

## On This Day shortcut

- NVDA+Windows+F12: Once for historical events, twice for births, three times for deaths, and four times for holidays and observances.

## Dhikr and alert shortcuts

- NVDA+Ctrl+Shift+F11: Enable or disable all automatic alerts.
- NVDA+Shift+F12: Repeat the last spoken alert.
- NVDA+Alt+F12: Announce the alert status.
- NVDA+Shift+F11: Enable or disable recurring Dhikr.

## Alarm shortcuts

- NVDA+Alt+F8: Open the personal alarm manager.
- NVDA+F8: Once to announce the next alarm, twice for the number of enabled alarms, and three times to stop the currently ringing alarm.
- NVDA+Shift+F8: Snooze the active alarm according to its snooze settings.

## Timer shortcuts

- NVDA+Alt+Y: Open the countdown timer manager.
- NVDA+Y: Once for the selected timer's name and remaining time, and twice for its state and the number of timers.
- NVDA+Shift+Y: Start, pause, or resume the selected timer.
- NVDA+Ctrl+Shift+Y: Restart the selected timer after confirmation.
- NVDA+Ctrl+Y: Silence a ringing timer and announce its name.
- NVDA+Windows+Y: Move to the next timer.
- NVDA+Windows+Shift+Y: Move to the previous timer.

## Stopwatch shortcuts

- NVDA+J: Start, pause, or resume timing.
- NVDA+Shift+J: Record a new lap.
- NVDA+Windows+Shift+J: Once for the current lap's duration and twice for the last recorded lap's duration.
- NVDA+Ctrl+J: Open the stopwatch window.
- NVDA+Ctrl+Shift+J: Reset the stopwatch to zero after confirmation.
- NVDA+Windows+J: Once for elapsed time and twice for the stopwatch's state and number of recorded laps.

## World clock shortcuts

- NVDA+Ctrl+F12: Once for the first city's time, twice for the second city's time, and three times for the third city's time in the favorites list.

## Commands without default shortcuts

Some Awqati commands are available in Input Gestures without default shortcuts. You can assign keys to them as needed.

These include:

- **Open date converter:** Once to open the simple converter and twice to open the advanced converter after a shortcut has been assigned.
- **Open weather information in a text window:** Display and copy the last successful weather report.

These features remain available through the add-on's interfaces without assigning shortcuts to them.

# Contributing and Contact

## Reporting bugs

If you encounter a problem with Awqati, you can report it through the project's GitHub repository. Describe the steps to reproduce it, the expected result, and the actual result.

It is advisable to include the NVDA and add-on versions and, when needed, attach diagnostic information after reviewing its contents.

## Suggesting improvements

We welcome suggestions for developing the add-on and improving its features and accessibility. You can submit them through the issues and suggestions section of the project repository.

Please explain the need for the proposed feature and how you expect to use it.

## Contributing to development

Awqati is an open-source project. Developers can review its code and contribute bug fixes, feature development, and improvements to tests and documentation, following the procedures in the project repository.

## Helping translate Awqati

The add-on currently supports Arabic and English, and we welcome contributions to add new languages. Our goal is for this add-on to reach every blind person around the world who could benefit from it, in their native language.

Contributions include translating the interfaces, messages, and help guide while maintaining accurate, consistent terminology and ensuring that the text is presented correctly in NVDA.

## Official project links

- **Project repository:** [https://github.com/alialomari-coder/Awqati](https://github.com/alialomari-coder/Awqati)
- **Releases and downloads:** [https://github.com/alialomari-coder/Awqati/releases](https://github.com/alialomari-coder/Awqati/releases)
- **Bug reports and suggestions:** [https://github.com/alialomari-coder/Awqati/issues](https://github.com/alialomari-coder/Awqati/issues)
- **Email:** [alialomary@gmail.com](mailto:alialomary@gmail.com)

# Change Log

## **Version 8.2.2:** Fixes and improvements to the add-on’s performance and the stability of its features.

## Version 8.2.1

- Improved the wording of detailed Arabic weather reports, dividing the information into shorter, clearer sentences.
- Improved descriptions of periods when no rain is expected, including periods extending into the following day.
- Clarified the meaning of the highest precipitation probability and improved the announcement of percentages.

## Version 8.0.2

- Improved the presentation of weather reports and text windows and the copying of information.
- Improved the wording of today's forecast and times on the following day.
- Reduced repeated announcements of zero precipitation probabilities while retaining full details in the text report.

## Version 8.0.0

- Added the optional weather service, with current conditions and daily and hourly forecasts.
- Added support for detail levels, customizable information, and units of measurement.
- Added text reports that can be copied and an optional weather summary within day information.

## Version 7.1.0

- Expanded the daily astronomical synopsis with more information about the Sun, Moon, and seasons.
- Added meridian transit, altitude, distance, and lunar phase timing data.
- Improved the presentation of astronomical information and text windows while keeping the traditional calendar section separate.

## Version 7.0.0

- Added the simple and advanced date converters.
- Added support for conversion between Gregorian, Lunar Hijri, and Julian calendars using the available methods.
- Added a results window for copying the converted date and reversing the conversion.

## Version 6.0.0

- Added the Wikipedia-based On This Day service.
- Added support for historical events, births, deaths, holidays, and observances in Arabic and English.
- Provided direct narration and browsable web pages, with daily information storage.

## Version 5.0.0

- Added four time management tools: alarms, countdown timers, a stopwatch, and a world clock.
- Added support for managing multiple alarms and timers, recording laps, and favorite cities.
- Added keyboard shortcuts for controlling the new tools.

## Version 4.0.0

- Rebuilt the add-on and changed its name from Prayer Times to Awqati.
- Developed the calculation of prayer times and Iqama, and the Zawali and Ghurubi clocks.
- Added support for five calendars, astronomical information, the traditional Arabian calendar, and Qibla direction.
- Developed the Dhikr, alert, and quiet hours system.
- Added a worldwide location database and support for Arabic and English.

Details of earlier versions are available in the project's historical change log.
