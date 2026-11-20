# Overview

Awqati is an NVDA add-on that brings together prayer times, timekeeping, calendars, and astronomical and weather information. Its tools and alerts help users organize their time and keep track of their day.

The add-on provides prayer times, sunrise, midnight and the start of the last third of the night, with customizable calculation methods and alerts. It also offers a clock with Zawali and Ghurubi time, and five calendars: Gregorian, Lunar Hijri and three Solar Hijri calendars.

Awqati presents daily information about the Sun, Moon and seasons, alongside information from the traditional Arabian calendar, including Talaa periods, seasons and the Suhail year. Its weather service provides current conditions and forecasts for today and the coming days, with two detail levels and options for customizing information and measurement units.

It provides alerts for prayer times, daily Wird and adhkar, as well as Qibla direction information, with customizable alerts and quiet hours.

Awqati includes four time management tools: alarms, countdown timers, a stopwatch and a world clock, with dedicated keyboard shortcuts for controlling them and checking their status.

It also offers On This Day information from Wikipedia, which can be read directly or browsed in web pages.

Awqati supports Arabic and English, with keyboard shortcuts and interfaces accessible to screen readers.

# How to use the add-on

The Awqati settings page contains a fixed section that is always displayed and another section whose options change according to the selected settings category.

The fixed section contains location settings, the master switch for enabling all automatic alerts, quiet-hours settings, and buttons for general functions such as copying diagnostic information and checking for data updates.

The changing section contains five main categories: Prayer times, Clock, Calendar, Weather, and Dhikr alerts. When one of these categories is selected, its options appear and the options for the other categories leave the navigation order.

## Setting the location

Some add-on functions, such as prayer times, the Ghurubi clock, Qibla direction, and astronomical information, depend on the assigned location.

When the add-on runs for the first time, a window for setting the location appears. You may cancel it and choose the location later from the add-on settings.

You can set the location in one of the following ways:

1. Choose from the list: select the country and then the city. You can type and search in both the country and city lists.
2. Detect the location automatically: when the user selects this function, the add-on asks Windows to detect the location, then presents the result so that the user can accept or reject it.
3. Enter a custom location: type the location name, its coordinates, and its time zone. This lets the add-on be used in places that are not included in the city database.

When saving a custom location with Automatic by country, Awqati asks you to choose an explicit calculation method from a list; it does not infer a country or choose a method for you. Cancelling preserves existing data. The same prompt appears on startup for older settings in this state. A saved manual method is retained.

## Showing the Qibla direction

The Qibla direction is shown using the location assigned in the add-on. It states the general direction, the amount of deviation, and the precise bearing calculated from true north.

Because a computer cannot know the direction in which the user or device is facing, practical use of this information requires knowing which way north lies at the user's location. We therefore generally recommend confirming the direction of north and treating this service as guidance.

## Enabling all automatic alerts

This is the master switch that controls every automatic alert issued by the add-on, including prayer-time, clock, and dhikr alerts.

When it is disabled, all automatic alerts stop without their settings being deleted. When it is enabled again, alerts enabled in their own sections resume working.

## Enabling quiet hours

This option lets the user stop alerts during a specified period, such as sleeping or rest time, while preserving all settings. Alerts resume after the quiet period ends.

Additional settings control how quiet hours apply to prayer-time alerts.

## Copying diagnostic information

This button copies a technical report about the add-on's status, settings, and environment to the clipboard for use when reporting a problem or requesting support. Sensitive information that does not need to be shared is excluded.

## Checking for data updates

This button checks whether newer versions of the add-on data are available, including location, time-zone, calculation-method, and Arabian-calendar data.

This button checks general data only on request. World clock has a separate update channel with an optional weekly automatic check, described in its section.

# Add-on settings sections

In addition to the fixed section, the Awqati settings contain five main categories: Prayer times, Clock, Calendar, Weather, and Dhikr alerts.

Prayer times is selected by default when the settings open. When another category is selected, the current category's options disappear and the selected category's options appear in their place.

## Prayer times

This section contains settings for prayer times and related times, as well as the alert settings for each time.

### Enabling prayer-time alerts

This option enables or disables alerts associated with prayer times and the other times, including alerts before the time begins, alerts when it begins, Iqama alerts, and after-time alerts.

When it is disabled, these alerts stop while their settings are preserved. They resume when it is enabled again.

### Opening the Today's prayer times window

This button opens a window that presents all of today's prayer times in a form that can be read, reviewed, and copied.

### Verifying today's prayer times online

This button compares the prayer times calculated within the add-on with the times from an external online provider. It shows the differences without automatically changing the internal prayer times.

### Prayer-time calculation method

This setting chooses the method used to calculate prayer times. The user may select the method that is appropriate or leave the setting on Automatically by country.

### Asr calculation

This setting chooses the juristic method used to calculate the beginning of Asr. The Majority option follows the method known among the Shafi'i, Maliki, and Hanbali schools, while the Hanafi option follows the Hanafi method for calculating the beginning of Asr.

### High-latitude handling

This setting controls how the add-on handles places where twilight lasts a long time or where Fajr and Isha are difficult to calculate in the usual way. The Automatic option lets the add-on apply the appropriate policy for the situation.

### Duration for which the current prayer remains current after Iqama, in minutes

This setting determines how long a prayer remains classified as the current prayer after its calculated Iqama time. The default is 20 minutes.

### Time to configure

This option selects the time whose individual settings you want to change.

The list contains the following eight times: Fajr, Sunrise, Dhuhr, Asr, Maghrib, Isha, Midnight, and the Last Third of the night.

### Settings for the selected time

When one of the times is selected from the Time to configure list, the settings for that time appear.

Some options differ according to the selected time. The five prayers have Iqama-related settings, while Sunrise, Midnight, and the Last Third have independent after-time alerts.

### Time correction in minutes

This setting lets the calculated time be moved earlier or later by a number of minutes when needed.

The default is zero, and changing it is not recommended unless necessary.

### Alert before the time begins

This option sets how many minutes before the time begins the advance alert is issued.

The default is ten minutes, and the user can change it as needed.

### Action for the alert before the time begins

This setting chooses how the advance alert is presented. The available options are:

- Mute.
- Speech only.
- Sound file only.
- Sound file and speech.

When an action that includes a sound file is selected, options to choose, preview, and remove the file appear.

### Action for the alert when the time begins

This setting chooses how the alert is presented when the time begins. The available choices are mute, speech, a sound file, or a sound file with speech.

### Iqama settings for the five prayers

When one of the five prayers is selected, additional Iqama settings appear.

### Time between Adhan and Iqama

This value sets the period between the beginning of the prayer time and the calculated Iqama time.

The defaults are:

- Fajr: 25 minutes.
- Dhuhr: 20 minutes.
- Asr: 20 minutes.
- Maghrib: 10 minutes.
- Isha: 20 minutes.

These values can be changed to suit the mosque, country, or user's preferences.

### Alert before Iqama

This setting determines how many minutes before Iqama the alert is issued. The default is five minutes.

### Action for the alert before Iqama

This setting chooses how the alert before Iqama is presented. The available choices are mute, speech, a sound file, or a sound file with speech.

### After-time alerts for the other times

When Sunrise, Midnight, or the Last Third is selected, an independent after-time alert setting appears.

This setting chooses the delay after which the alert is issued and the action used to present it.

## Clock

This section contains settings for the Zawali and Ghurubi clocks, automatic clock alerts, and the four time tools described below.

### Choose clock settings

This option selects the type of clock whose settings you want to customize, either the Zawali clock or the Ghurubi clock. The settings for the selected type then appear.

The Zawali clock is ordinary civil time. The Ghurubi clock starts at sunset: nighttime hours begin at sunset and are followed by daytime hours until the next sunset. It is an Arabic time system that was used historically.

### Announcement format

This setting chooses the level of detail used when announcing the time. The user can select among the available formats according to the amount of information they prefer to hear.

### Hour system

This setting chooses whether the time is displayed and announced using the 12-hour or 24-hour system.

### Announcement representation

This setting chooses whether the time is read in words or digits.

### Announce seconds

This option includes seconds in the time announcement or limits it to hours and minutes.

### Announce “zero minutes”

This setting chooses whether the add-on says “zero minutes” when the minute is zero or announces only the hour.

### Preview announcement

This button lets the user hear the time according to the current clock settings before saving changes.

### Enabling automatic clock alerts

This option starts or stops alerts for parts of the hour while preserving their settings when disabled.

Alerts can be selected for one or more of the following times:

- Quarter past the hour.
- Half past the hour.
- Three quarters past the hour.
- On the hour.

### Clock-alert action

This setting chooses how the clock alert is presented. The available options are:

- Speech only.
- Sound file only.
- Sound file and speech.

The add-on includes a default sound file for clock alerts. The user can also choose, preview, or remove a custom sound file.

### The four time tools

### Opening tools from Clock settings

Press NVDA+Alt+A to open Awqati settings. Select Clock in the settings sections list, then Tab to Time tools. Use the arrows to choose Alarms, Timers, Stopwatch or World clock, in that list order. Focus stays on the selector; Tab enters the selected tool and Shift+Tab returns. Hidden tools leave the Tab order. Selections and input are retained while switching tools, and the last tool is remembered for the NVDA session.

The alarm, timer and stopwatch opening shortcuts select the same embedded tools in Clock settings. Time tool changes are saved immediately, independently of Apply and Cancel in Awqati settings. Closing settings does not stop alarms, measurement or countdowns.

### Alarms

Add an alarm, enter its name, hour (0–23) and minute (0–59), and select at least one repeat day. Midnight, 00:00, is valid. In the weekday list, use arrows to move and Space to select or clear a day. All seven days means daily recurrence. There is no once-only mode.

Each alarm has its own speech/sound action, optional custom WAV, ringing duration, snooze interval and count, and quiet-hours option. Alarms bypass quiet hours by default, but obey the global automatic-alert switch. Stop ends the current ringing cycle; Snooze postpones it for the saved interval. Stopping never creates a snooze. Disabling, editing or deleting an alarm cancels its pending snooze.

Alarms follow Windows local time and time zone, independently of the prayer location. During daylight-saving transitions, missing times move to the first valid minute and repeated times run once. Late events have a ten-minute grace period; a previously started ringing cycle is not replayed after restarting NVDA. Prayer alerts interrupt ringing, and simultaneous alarms wait in the central queue. Alerts cannot run while the computer or NVDA is off.

### Timers

Create a timer, enter an optional name and hours, minutes and seconds, then start it. Run several timers and save reusable definitions. The maximum is 999 hours, 59 minutes and 59 seconds; zero is rejected. Select a timer to start, pause, resume, restart, cancel, edit or delete it. Cancel an active cycle before editing. Restarting from the original duration always requires confirmation, defaulting to No; deletion also requires confirmation.

Choose speech, sound or both, an optional custom WAV, and one alert or repetitions at a chosen interval. Preview the sound when needed. Play clock ticking is off by default; only the selected running timer ticks. Higher-priority alerts and previews silence ticking while other timers keep running. Silencing a ringing timer stops one timer's sound and pending repetitions, regardless of selection, and leaves its state Finished.

Next and Previous wrap in list order without starting or stopping timers. Closing settings retains selection and ticking for the session. The double-press query counts all timers, including saved and finished timers. Counting includes sleep and ignores Windows clock changes during the session. Running timers are restored after restarting NVDA using UTC; changing the clock while NVDA is off can affect restoration. Late alerts have a ten-minute grace period without a catch-up burst. The global switch suppresses expiry output without stopping counting. Timers bypass quiet hours by default, with a separate option per timer.

### Stopwatch

Start, pause or resume according to the current state. Record laps during measurement, review the native list of lap numbers, durations and cumulative totals, or copy results as text. The current-lap query reports time since the last lap, or total elapsed time before the first lap. Queries do not change measurement or results. A running stopwatch cannot be reset: pause it, then confirm resetting. No is selected by default.

Choose Tones only, Speech only, Tones and speech, or No confirmation sounds for operations. Preview confirmation tones without changing measurement. Display updates are silent. Measurement includes computer sleep and ignores civil-clock changes. After restarting NVDA, the stopwatch is restored paused at its last saved value without guessing time while NVDA was absent. An unexpected crash may lose time since the last save.

### World clock

Choose Add city, search in Arabic or English, and add a city to your list. Use arrows to move between cities and the available commands to sort, reorder or delete with confirmation. List order determines the first three cities queried by the shortcut; queries do not change selection. Times are calculated from UTC using each city's time zone and daylight-saving rules, independently of the prayer location.

To customize a city or country name, press the Applications key or Shift+F10 and choose Edit name. Save or cancel changes, or restore original names and save. Arabic and English names are saved independently without changing time zones or calculations.

Update data checks the official signed channel manually in the background. Update data automatically is enabled by default and checks weekly, waiting at least one minute after startup before connecting. Disable it to keep manual checks only. Automatic checks stay silent when there is no update or a failure; an actual update is announced after important Awqati alerts finish. Cities, ordering, names and offline operation are preserved if an update fails. Updates activate without restarting NVDA. This channel is separate from the general add-on data-update button.

## Calendar

This section contains settings for calendars, date-display formats, and daily information.

### Date converter

In Awqati settings, choose Calendar, Tab to “Open date converter” or “Advanced conversion...”, and press Enter.

In the basic converter, select the direction, day, month and year, then Convert. Hijri conversion uses the bundled Umm al-Qura table and reports dates outside its supported range. Today fills the current date for the saved location; Advanced... opens the expanded options.

The advanced converter offers Hijri, Gregorian and Julian source and target calendars, Umm al-Qura and historical arithmetic IIc in the dialog. The internal engine implements eight arithmetic variants for verification; the dialog exposes these two reference choices. Select the method and enter the day, month and year. The reference depends on the method; historical arithmetic does not establish religious moon sightings. The method selector is disabled when neither calendar is Hijri.

The shared result window contains the original date, converted date and reference. Copy result copies the target date; Reverse conversion swaps the two dates and updates the converter fields when the result closes. Use Tab and Shift+Tab to navigate, Enter to convert and Escape to close. The converter does not apply your personal Hijri correction or change saved settings.

“Open date converter” in the Awqati Input Gestures category has no default shortcut. Open the NVDA menu, Preferences, Input Gestures, select the command and add an unused shortcut. Once assigned, one press opens the basic converter; two quick presses open the advanced converter after NVDA’s configured multi-press timeout. Change or remove the shortcut in the same dialog.

### Primary calendar

This setting chooses the calendar that the add-on uses as the primary date when presenting date information. The choices are the Lunar Hijri calendar and the Gregorian calendar.

The Lunar Hijri calendar is the default primary calendar.

### Include Arabian-calendar information in daily information

This option adds traditional Arabian-calendar information to the astronomical daily information when enabled.

### Opening the Daily information window

This button opens a window that presents daily information in a form that can be read, reviewed, and copied.

### Astronomical synopsis in version 7.1.0

The scientific synopsis presents five connected paragraphs for the assigned location, date and time:

- Day and night length, daylight change since the previous solstice, and the longest day and longest night on their actual respective dates.
- Solar meridian transit time and altitude at transit, and the current distance between the centres of Earth and the Sun.
- Lunar phase, illuminated percentage and approximate age, and the current distance between the centres of Earth and the Moon.
- Moonrise and moonset in chronological order, lunar meridian transit and altitude at transit, followed by the time of the actual maximum altitude; the maximum may occur at a different time from transit.
- The next new moon, first quarter, full moon and last quarter, in chronological order.

The text states when no rise or set occurs during the day or a value cannot be calculated, rather than assuming an event time. A ΔT time-scale note appears where needed. Event times are calculated within the models' limits and do not establish crescent visibility. Traditional Arabian-calendar information remains a separate optional section; no new detail levels are introduced.

For keyboard access, open Awqati settings with NVDA+Alt+A, choose Calendar, Tab to the button that opens Daily information, and press Enter. Press NVDA+Ctrl+H once to speak astronomical information, twice for Arabian-calendar information, or three times within NVDA's multi-press timeout to open the Daily information window. Three presses of NVDA+F12 also speak Daily information according to the heritage inclusion option. Shortcuts can be reassigned under Awqati in Input Gestures.

The window focuses a read-only text field named after the window. Read with the arrow keys, use Control+Home to reach the start, or Control+A then Control+C to copy all text. Press Escape to close, or Tab to Close and press Enter. Focus returns to the opening control when it remains available.

### Choose the calendar to configure

This setting chooses the calendar whose options you want to customize. Its options appear without affecting the settings of the other calendars.

The add-on includes five calendars:

- Lunar Hijri calendar.
- Gregorian calendar.
- Saudi Solar Hijri calendar.
- Afghan Solar Hijri calendar.
- Persian Solar Hijri calendar.

Only the Lunar Hijri and Gregorian calendars can be selected as the primary calendar. The three solar calendars remain independent additional calendars.

### Date format

This setting chooses how the selected calendar's date is displayed and announced. Available formats include Double, Full, Moderate, and Short.

### Lunar Hijri date correction

This option moves the Lunar Hijri date forward or backward by a number of days when needed to match the locally adopted date.

The default is zero, meaning that no correction is applied.

### Preview announcement

This button lets the user hear a sample date according to the current calendar and settings before saving changes.

The add-on also provides Daily information, which brings together the day's astronomical information and can include traditional Arabian-calendar information when its option is enabled.

## Weather

### About the service

Weather provides current conditions and forecasts for today, the upcoming hours and the coming days, using the saved Awqati location and time zone. It is optional, disabled by default and requires an Internet connection to retrieve data. No separate location, account or API key is needed.

### Enabling weather

Press NVDA+Alt+W to open Awqati settings with Weather selected, even while the service is disabled. Select “Enable weather service” and save with Apply or OK. Alternatively, press NVDA+Alt+A, which opens general settings at Prayer times, then choose Weather in the section selector.

To disable the service, clear its checkbox and save. Updates stop and in-flight results are ignored; your choices remain saved. Cancelling settings or a customization dialog discards its edits.

### Requesting weather information

- NVDA+W once: current weather.
- NVDA+W twice: today's forecast and upcoming hours.
- NVDA+W three times: coming days forecast.

After the last press, wait for NVDA's multi-press timeout plus 50 milliseconds, with a minimum total of 300 milliseconds. Reports wait until the sequence settles. Additional presses beyond three in the same sequence select coming days. Detail level is set in settings and is independent of press count. Reassign the command in the Awqati category of Input Gestures if needed.

The three reports are also available under NVDA menu, Tools, Awqati, Weather, alongside “Open weather information in a text window” and “Refresh now”.

### Detail levels

Brief is the default. Current weather includes the city in the report language, conditions, current temperature and today's expected high and low. Detailed adds wind and the available additional information you select. Temperatures are rounded to the nearest integer in Brief and to one decimal place when needed in Detailed, including kelvin. Exact halves round away from zero; the original values remain unchanged.

Current conditions say sunny only when daytime is confirmed, and clear at night or when daytime information is unavailable; daily descriptions are neutral. Today's and coming days forecasts include conditions, high, low and highest hourly precipitation probability; selected options extend Detailed reports. Unavailable values are omitted and genuine zero values are preserved.

### Customizing weather information

Under Displayed information, open Customize weather information and choose a category. Choices for the three categories are saved independently:

- Current weather: feels-like temperature, humidity, wind gusts, sea-level pressure, visibility, cloud cover, precipitation, UV index and U.S. air quality index.
- Today's forecast: precipitation amount, maximum wind speed, wind gusts and maximum UV index.
- Coming days forecast: the same daily options, saved separately.

These options extend Detailed reports and do not remove fixed core information. Feels-like temperature, humidity and gusts are enabled by default for current weather; precipitation amount and maximum wind are enabled for today and coming days. Other additions, including air quality and UV, are disabled by default.

Precipitation probability is a percentage; amount uses millimetres or inches. Current precipitation states the actual data interval, such as the last 15, 30 or 60 minutes, and is omitted without a known interval. Pressure is corrected to sea level. UV is a unitless index. Wind direction means the direction it comes from and is omitted for calm wind.

### Measurement units

- Metric, the default: Celsius, kilometres per hour, hectopascals, kilometres and millimetres.
- Imperial: Fahrenheit, miles per hour, inches of mercury, miles and inches.
- Custom: Customize units lets you choose each unit independently.

Available units are Celsius, Fahrenheit or kelvin for temperature; kilometres per hour, metres per second, miles per hour or knots for wind; hectopascals, millibars, millimetres of mercury or inches of mercury for pressure; kilometres or miles for visibility; and millimetres or inches for precipitation. Custom choices are retained when switching systems. Conversion uses original values locally without another connection.

### Daily and hourly forecasts

Choose two to six future days starting tomorrow; the default is two. Upcoming hours can be 3, 6 or 12; the default is 6. Include hourly periods in detailed report is enabled by default. These details appear in today's forecast, rather than current weather.

Readings span the full horizon: hourly for 3 hours, every two hours for 6, and every three hours for 12, including the last available sample. They are point-in-time samples rather than whole-period averages. Tomorrow is stated across midnight, other days use local dates, and a UTC offset distinguishes repeated daylight-saving hours. With hourly periods disabled or Brief selected, the report gives the first significant expected change; stability across the full horizon is reported only when all required data are present.

If precipitation probability is zero in every available hour, speech uses one statement identifying the available readings' time range and omits repeated zeros from samples. The text keeps individual probabilities. Missing values are never treated as zero, and positive probabilities between displayed samples also prevent this reduction.

### Open weather information in a text window

Request the desired report with NVDA+W or the menu and wait for success. Then select Open weather information in a text window from the Weather menu. The same name is available in Input Gestures without a default shortcut.

The window opens a saved text version of the last successfully requested information, preserving its report type, detail level, units, time and location, with hourly details and attribution. Opening it neither retrieves data nor recalculates the report. A failed request leaves the last successful version intact. With no earlier successful request, a message asks you to request a report first. The version lasts for the NVDA session, including after settings change, and may no longer describe current conditions.

Use arrows to read, Control+Home for the start, Control+End for the end, Control+A to select all and Control+C to copy selected text. Tab moves from the text to Copy report, Close, and Data source and licence; Shift+Tab reverses this order. Copy report copies the entire text including attribution without a selection. Escape closes the window and restores the opener's focus.

Open text never updates automatically. Opening the window while it exists focuses its preserved text, even after another report request. Close and reopen it to review the last successful report. Prayer and other information windows remain independent.

### Including weather in daily information

Include weather conditions in daily information is disabled by default and follows the selected detail level and current-weather options. It uses valid cached data after astronomy and Arabian calendar information without appending full hourly or multi-day forecasts. It never delays daily information while waiting for a connection. Without valid cached data, ordinary daily information remains available and a silent retrieval starts for the next reading.

### Updating information

Under General settings, choose automatic refresh every 15, 30 or 60 minutes; the default is 30. Automatic updates are silent. Refresh now uses saved settings, so apply edits first. It is also available in the Weather menu. Manual refresh cannot repeat within a minute and respects source limits and Retry-After.

Please wait is spoken once when retrieval is needed, and never for immediately available valid data. Only the latest request speaks on success. Ordinary reports omit the last update time. Weather cache validity follows the refresh interval; air quality has a separate one-hour cache. After retrieval fails, data less than two hours old may be used if their time coverage remains suitable, with a warning that cached data may be out of date. New queries never read expired data or data for an old location; the saved review text remains as previously requested. A clear message reports failure when no usable data exist. Air-quality failure does not prevent weather reports. Daily statistics that do not match local day boundaries at daylight-saving transitions may be omitted rather than assigned to the wrong period.

### Sources and privacy

Weather data are provided by [Open-Meteo](https://open-meteo.com/) under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Air quality uses [CAMS](https://atmosphere.copernicus.eu/) through Open-Meteo; see [air-quality attribution](https://open-meteo.com/en/docs/air-quality-api). Text is translated and summarized and units are converted. Attribution and source and licence links appear in the text report and source button, and are omitted from speech and daily information.

Enabling weather sends coordinates and time zone to Open-Meteo over HTTPS; the provider also sees your IP address. Your name and prayer settings are not sent. The provider may log coordinates and IP addresses; its policy describes deletion of service logs after 90 days. Requests are not anonymous. Weather is cached only in memory and is lost when NVDA exits. Enabling U.S. air quality makes a separate request even in Brief. This implementation does not use MET Norway.

Current conditions and forecasts are model estimates, rather than direct local station observations. Air-quality resolution differs from weather resolution; reports are neither medical advice nor official warnings. See [terms and privacy](https://open-meteo.com/en/terms) and [service limits](https://open-meteo.com/en/pricing). The free endpoint is for non-commercial use, has shared limits and no continuity guarantee; distributing an application for free does not automatically qualify it for commercial use of that endpoint.

Settings migration and rollback: loading 7.1.0 settings upgrades schema 1 to 2 in memory with weather disabled and existing choices preserved. Before the first save, settings.json.schema1.bak is created beside settings.json, followed by an atomic save. A read, migration, backup or replacement failure does not replace the original file with defaults. Upgrading 8.0.0 settings adds only the enabled feels-like option and does not rewrite the file merely by reading it.

To return to 7.1.0, close NVDA, keep the new settings.json under another name, restore settings.json.schema1.bak as settings.json inside awqati in the NVDA configuration directory, then install 7.1.0. Do not let it read schema 2 directly. If the new settings were never saved, restoration is unnecessary. Do not delete time-tool data.

## Dhikr alerts

This section controls alerts related to adhkar and the daily Wird, including their times and presentation methods.

### Enabling dhikr alerts

This is the master switch for dhikr alerts. When it is disabled, every alert in this section stops while its settings are preserved. When it is enabled again, the enabled functions within the section resume working.

Dhikr alerts contain five independent functions: morning adhkar, evening adhkar, the Friday Hour, the daily Wird, and recurring dhikr reminders.

All five functions are disabled by default, and each can be enabled independently.

### Morning adhkar

The morning-adhkar alert can be scheduled after Fajr, before Sunrise, or after Sunrise, with a number of minutes relative to the chosen time.

The default is fifteen minutes before Sunrise.

### Evening adhkar

The evening-adhkar alert can be scheduled after Asr, before Maghrib, or after Maghrib, with a number of minutes relative to the chosen time.

The default is fifteen minutes before Maghrib.

### Friday Hour

This reminder runs on Friday. It can be scheduled after Asr or before Maghrib, with a number of minutes relative to the chosen time.

The default is sixty minutes before Maghrib.

### Daily Wird

This option sets a fixed time each day for the Wird reminder. The default is 10:00 PM, and the reminder time and text can be changed.

### Alert action

For morning adhkar, evening adhkar, the Friday Hour, and the daily Wird, one of the following actions can be selected:

- Speech only.
- Sound file only.
- Sound file and speech.

When an action that includes a sound file is selected, options to choose, preview, and remove the file appear.

### Enabling recurring adhkar

This option starts a recurring reminder that cycles through a number of adhkar. The default interval between reminders is sixty minutes and can be changed according to the user's preference.

Each dhikr within the cycle can be enabled or disabled independently, and each can have its own action.

Two alert methods are available for recurring reminders:

- Speech only.
- Sound file only.

The first reminder begins after the configured interval has fully elapsed. The cycle then moves only among enabled adhkar.

# Data, installation and upgrades

Time tools save their data in the awqati folder inside the NVDA configuration directory. Upgrading preserves your settings and data. Back up this folder before upgrading.

To install, open the nvda-addon package, follow NVDA's instructions and restart NVDA. Disable or remove Awqati through the installed add-ons list in NVDA's Add-on Store. Updating the package does not require deleting time tool data.

# Approved keyboard shortcuts

NVDA is your screen reader modifier; Windows is the Windows logo key. For double or triple presses, press the key successively while holding the modifiers. You can assign additional commands under Awqati in NVDA’s Input Gestures dialog; your saved bindings are preserved. NVDA+F12 overlaps with a built-in NVDA command; you can reassign it if needed.

Each shortcut is listed only under its first function; its description includes all multi-press actions.

## General shortcuts

- NVDA+Alt+a: Open Awqati settings.

## Weather shortcut

- NVDA+Alt+W: Open Awqati settings with Weather selected, even when the service is disabled.

- NVDA+W: Press once to announce the current weather, twice to announce today's weather forecast, or three times to announce the weather forecast for the coming days.

## Prayer-time shortcuts

- NVDA+f11: Press once to announce current time details, twice to announce the previous time, or three times to announce today's prayer times.
- NVDA+Shift+p: Verify today's prayer times online.
- NVDA+Alt+p: Open today's prayer times window.

## Clock and time shortcuts

- NVDA+f12: Press once to announce the time, twice to announce the primary-calendar date, or three times to announce daily information.
- NVDA+g: Press once to announce Ghurubi time, twice to announce the Qibla direction, or three times to announce the assigned location.

## Calendar and date shortcuts

- NVDA+h: Press once to announce the Lunar Hijri date, twice to announce the Saudi Solar Hijri date, or three times to announce the Arabian calendar summary.
- NVDA+Shift+h: Press once to announce the Afghan Solar Hijri date or twice to announce the Persian Solar Hijri date.
- NVDA+Ctrl+h: Press once to announce astronomical daily information, twice to announce Arabian calendar daily information, or three times to open the daily information window.

## Alert and adhkar shortcuts

- NVDA+Ctrl+Shift+f11: Toggle all automatic alerts.
- NVDA+Shift+f12: Repeat the last spoken alert.
- NVDA+Alt+f12: Announce alert status.
- NVDA+Shift+f11: Toggle recurring dhikr.

## Alarm shortcuts

- NVDA+Alt+f8: Open personal alarms.
- NVDA+f8: Press once to announce the next personal alarm, twice for the enabled alarm count, or three times to stop the current alarm.
- NVDA+Shift+f8: Snooze the current personal alarm.

## Timer shortcuts

- NVDA+Alt+y: Open countdown timers.
- NVDA+y: Press once to announce the selected timer's name and remaining time, twice to announce its state and the number of timers.
- NVDA+Shift+y: Start, pause or resume selected countdown timer.
- NVDA+Ctrl+Shift+y: Restart selected countdown timer with confirmation.
- NVDA+Ctrl+y: Silence one currently ringing countdown timer and announce its name.
- NVDA+Windows+y: Select the next countdown timer and announce its name and remaining time.
- NVDA+Windows+Shift+y: Select the previous countdown timer and announce its name and remaining time.

## Stopwatch shortcuts

- NVDA+j: Start, pause or resume the stopwatch according to its current state.
- NVDA+Shift+j: Record a new stopwatch lap.
- NVDA+Windows+Shift+j: Press once to announce the current lap duration, or twice to announce the last recorded lap.
- NVDA+Ctrl+j: Open the stopwatch window.
- NVDA+Ctrl+Shift+j: Reset stopwatch with confirmation.
- NVDA+Windows+j: Press once to announce stopwatch elapsed time, or twice to announce its status and lap count.

## World-clock shortcuts

- NVDA+Ctrl+f12: Press once to announce the first city's time, twice for the second city's time, and three times for the third city's time.

# Sending feedback

We welcome your comments and suggestions. If you have any comments or suggestions, please contact us by email:

alialomary@gmail.com

# Change log

## Version 8.0.2

Updated overview and weather documentation; unified the text-window command and preserved the last successful report without fetching on open. Improved today’s opening and Arabic next-day times, and reduced repeated zero hourly rain probabilities in speech while retaining text details.

## Version 8.0.1

Improves weather reports, localized cities, daily extremes and hourly coverage; adds Copy report and direct weather settings.


## Version 8.0.0

Adds optional Open-Meteo weather, current conditions, today and coming days forecasts, hourly periods, custom units, accessible copyable reports and an optional daily synopsis summary. Requires Internet access when enabled; coordinates, time zone and IP address reach the provider. Weather is disabled by default. Migrates settings from 7.1.0 while preserving existing options. The name and internal identifier remain Awqati / awqati.

## Version 7.1.0

- Integrates the approved five-paragraph daily astronomical synopsis, including solar meridian transit and altitude, seasonal daylight changes, Earth-Sun distance, lunar rise/set and transit, independent maximum altitude, Earth-Moon distance and upcoming principal phases.
- Preserves the independent traditional Arabian calendar, existing settings, shortcuts and functions, with unchanged defaults.
- Fixes the report text field's accessible name and restores focus to its opener when closed.


## Version 7.0.0

- Added basic and advanced historical date converters, shared results, copying and reversal.
- Renamed Date settings to Calendar and added two converter buttons.
- Added an unassigned command: one press for basic, two for advanced once assigned.
- Preserved existing settings and shortcuts.

## Version 6.0.0

Adds On This Day while retaining every version 5 feature and time management tool.

- Wikipedia events, births, deaths, holidays and observances in Arabic and English.
- Direct narration and HTML pages accessible with NVDA, with original article links and section counts.
- Daily caching. Use NVDA+Windows+F12 with one to four presses.

## Version 5.0.0

This version introduces four new time management tools, along with improvements to performance, stability and ease of use.

- **Alarms:** Create multiple personal alarms, choose repeat days and alarm sounds, and snooze or stop ringing.
- **Timers:** Run multiple countdown timers at the same time, with options to pause, resume and restart them, customize their sounds and enable clock ticking.
- **Stopwatch:** Measure time, record laps, and review and copy the results.
- **World clock:** Check the time in cities around the world, add and reorder favorite cities, and customize their names, accounting for time zone differences and daylight saving time.
- **Keyboard shortcuts:** Add dedicated shortcuts for the new time tools, improve responsiveness and organize commands.
- **General improvements:** Enhance add-on stability, improve some interfaces, and update the Arabic and English help guides.

## Version 4.0.0

This version is a complete rebuild of the add-on formerly known as Prayer Times. Its name has changed to Awqati to reflect its wider range of functions.

- Rebuilt the add-on from scratch with a new architecture.
- Added a global location database, custom-location support, and automatic location detection.
- Enhanced the prayer-time engine and added Midnight, the start of the Last Third, and the Iqama system.
- Enhanced the Zawali and Ghurubi clocks, announcement formats, and related alerts.
- Added support for five calendars: Gregorian, Lunar Hijri, Saudi Solar Hijri, Afghan Solar Hijri, and Persian Solar Hijri.
- Added Qibla direction, daily astronomical information, and the traditional Arabian calendar.
- Rebuilt the alert, adhkar, daily-Wird, and quiet-hours systems.
- Enhanced sound-file and speech support and management of overlapping alerts.
- Added optional online verification of today's prayer times, add-on data updates, and diagnostics.
- Added Arabic and English support.
- Improved keyboard accessibility and integration with the NVDA screen reader.

## Version 3.2

- Changed automatic dhikr reminders from random selection to an ordered cycle.
- Added an interval that can be set in minutes.
- Simplified automatic reminder actions to Speech only or Sound file only.
- Refined interface terminology and standardized announcement formats and shortcuts.

## Version 3.1

- Added automatic dhikr reminders to the Dhikr alerts page.
- Added support for default and custom sound files for each dhikr.
- Improved sound playback and excluded disabled adhkar from reminders.

## Version 3.0

- Added the Dhikr alerts page.
- Added morning and evening adhkar, the Friday Hour reminder, and the daily Wird alert.
- Added custom sounds for dhikr alerts.

## Version 2.1

- Added the Clock page.
- Added Zawali and Ghurubi time.
- Added automatic clock alerts.
- Added multi-press shortcuts for time and date.
- Improved saving of clock and automatic-alert settings.

## Version 1.3

- Improved date formats.
- Fixed Lunar Hijri date correction.
- Added the Syriac month to the full Gregorian format.


## On This Day

Read historical events, births, deaths, and holidays and observances from Wikipedia in NVDA's language (Arabic or English), for your computer's local date. The first request needs an Internet connection; the saved data can then be reused offline for that day. Wikipedia text is neither translated nor replaced with another language when unavailable.

NVDA+Windows+F12: press once for events, twice for births, three times for deaths, or four times for holidays and observances. Repeat within NVDA's configured multi-press timeout. Later presses in the same sequence repeat observances; a pause beyond the timeout starts again at events. Reassign the command under Awqati in NVDA's Preferences, Input Gestures dialog.

Direct speech is the default. All items in the selected section are spoken without URLs. Control stops reading. Shift pauses/resumes where supported by NVDA and your synthesizer settings. Choosing another section stops the previous reading.

To use a local web page in your default browser, open Awqati settings with NVDA+Alt+A, choose Calendar, and Tab to “Show On This Day information in a web page instead of speaking it”. Toggle with Space and save with OK or Apply. The preference survives an NVDA restart. Clear the checkbox to return to speech. Web mode waits until the multi-press timeout plus a 100 ms margin after the last press, so one rapid sequence opens only the final section.

In NVDA Browse Mode, use H for headings, 1 for the main heading, K for links, L for lists, and I for list items. Add Shift to move backwards. Use arrows or your usual Say All command to read, Enter to follow a Wikipedia link, and Alt+Left to go back. Standard browser commands support selecting (Control+A), copying (Control+C), and printing (Control+P). Quick navigation depends on Browse Mode and your NVDA configuration.

An unavailable section produces “Information is unavailable in the selected language.” Connection and extraction failures have separate messages. No empty page or outdated day is presented as today's information. Local pages live in on_this_day_pages under Awqati's user data in the NVDA configuration directory. Each section's file is replaced when opened again; its date remains explicit in the page title.


On This Day pages include a section count. Each historical event or person has a separate item with its year; original observance groups use headings excluded from the count. “Please wait.” is spoken only if results take longer; fast memory and disk retrieval stays silent.
