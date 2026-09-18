# Overview

The Awqati add-on for the NVDA screen reader provides a range of services related to time, date, prayer times, and Qibla direction, together with reminders for daily devotional readings and adhkar throughout the day, with multiple options for controlling alerts and quiet hours.

The add-on includes a complete system for managing the five daily prayer times, as well as Sunrise, Midnight, and the Last Third.

It also includes two clocks, Zawali and Ghurubi, and five calendars: Gregorian, Lunar Hijri, Saudi Solar Hijri, Afghan Solar Hijri, and Persian Solar Hijri.

The add-on also provides Qibla direction, daily astronomical information, and other information derived from the traditional Arabian calendar, in addition to alerts for morning adhkar, evening adhkar, the Friday Hour, the daily Wird, and recurring adhkar, according to the user's preferences.

## How to use the add-on

The Awqati settings page contains a fixed section that is always displayed and another section whose options change according to the selected settings category.

The fixed section contains location settings, the master switch for enabling all automatic alerts, quiet-hours settings, and buttons for general functions such as copying diagnostic information and checking for data updates.

The changing section contains four main categories: Prayer times, Clock, Date, and Dhikr alerts. When one of these categories is selected, its options appear and the options for the other categories leave the navigation order.

### Setting the location

Some add-on functions, such as prayer times, the Ghurubi clock, Qibla direction, and astronomical information, depend on the assigned location.

When the add-on runs for the first time, a window for setting the location appears. You may cancel it and choose the location later from the add-on settings.

You can set the location in one of the following ways:

1. Choose from the list: select the country and then the city. You can type and search in both the country and city lists.
2. Detect the location automatically: when the user selects this function, the add-on asks Windows to detect the location, then presents the result so that the user can accept or reject it.
3. Enter a custom location: type the location name, its coordinates, and its time zone. This lets the add-on be used in places that are not included in the city database.

### Showing the Qibla direction

The Qibla direction is shown using the location assigned in the add-on. It states the general direction, the amount of deviation, and the precise bearing calculated from true north.

Because a computer cannot know the direction in which the user or device is facing, practical use of this information requires knowing which way north lies at the user's location. We therefore generally recommend confirming the direction of north and treating this service as guidance.

### Enabling all automatic alerts

This is the master switch that controls every automatic alert issued by the add-on, including prayer-time, clock, and dhikr alerts.

When it is disabled, all automatic alerts stop without their settings being deleted. When it is enabled again, alerts enabled in their own sections resume working.

### Enabling quiet hours

This option lets the user stop alerts during a specified period, such as sleeping or rest time, while preserving all settings. Alerts resume after the quiet period ends.

Additional settings control how quiet hours apply to prayer-time alerts.

### Copying diagnostic information

This button copies a technical report about the add-on's status, settings, and environment to the clipboard for use when reporting a problem or requesting support. Sensitive information that does not need to be shared is excluded.

### Checking for data updates

This button checks whether newer versions of the add-on data are available, including location, time-zone, calculation-method, and Arabian-calendar data.

Data updates are never checked automatically; the check runs only at the user's request.

## Add-on settings sections

In addition to the fixed section, the Awqati settings contain four main categories: Prayer times, Clock, Date, and Dhikr alerts.

Prayer times is selected by default when the settings open. When another category is selected, the current category's options disappear and the selected category's options appear in their place.

### Prayer times

This section contains settings for prayer times and related times, as well as the alert settings for each time.

#### Enabling prayer-time alerts

This option enables or disables alerts associated with prayer times and the other times, including alerts before the time begins, alerts when it begins, Iqama alerts, and after-time alerts.

When it is disabled, these alerts stop while their settings are preserved. They resume when it is enabled again.

#### Opening the Today's prayer times window

This button opens a window that presents all of today's prayer times in a form that can be read, reviewed, and copied.

#### Verifying today's prayer times online

This button compares the prayer times calculated within the add-on with the times from an external online provider. It shows the differences without automatically changing the internal prayer times.

#### Prayer-time calculation method

This setting chooses the method used to calculate prayer times. The user may select the method that is appropriate or leave the setting on Automatically by country.

#### Asr calculation

This setting chooses the juristic method used to calculate the beginning of Asr. The Majority option follows the method known among the Shafi'i, Maliki, and Hanbali schools, while the Hanafi option follows the Hanafi method for calculating the beginning of Asr.

#### High-latitude handling

This setting controls how the add-on handles places where twilight lasts a long time or where Fajr and Isha are difficult to calculate in the usual way. The Automatic option lets the add-on apply the appropriate policy for the situation.

#### Duration for which the current prayer remains current after Iqama, in minutes

This setting determines how long a prayer remains classified as the current prayer after its calculated Iqama time. The default is 20 minutes.

#### Time to configure

This option selects the time whose individual settings you want to change.

The list contains the following eight times: Fajr, Sunrise, Dhuhr, Asr, Maghrib, Isha, Midnight, and the Last Third of the night.

#### Settings for the selected time

When one of the times is selected from the Time to configure list, the settings for that time appear.

Some options differ according to the selected time. The five prayers have Iqama-related settings, while Sunrise, Midnight, and the Last Third have independent after-time alerts.

#### Time correction in minutes

This setting lets the calculated time be moved earlier or later by a number of minutes when needed.

The default is zero, and changing it is not recommended unless necessary.

#### Alert before the time begins

This option sets how many minutes before the time begins the advance alert is issued.

The default is ten minutes, and the user can change it as needed.

#### Action for the alert before the time begins

This setting chooses how the advance alert is presented. The available options are:

- Mute.
- Speech only.
- Sound file only.
- Sound file and speech.

When an action that includes a sound file is selected, options to choose, preview, and remove the file appear.

#### Action for the alert when the time begins

This setting chooses how the alert is presented when the time begins. The available choices are mute, speech, a sound file, or a sound file with speech.

#### Iqama settings for the five prayers

When one of the five prayers is selected, additional Iqama settings appear.

#### Time between Adhan and Iqama

This value sets the period between the beginning of the prayer time and the calculated Iqama time.

The defaults are:

- Fajr: 25 minutes.
- Dhuhr: 20 minutes.
- Asr: 20 minutes.
- Maghrib: 10 minutes.
- Isha: 20 minutes.

These values can be changed to suit the mosque, country, or user's preferences.

#### Alert before Iqama

This setting determines how many minutes before Iqama the alert is issued. The default is five minutes.

#### Action for the alert before Iqama

This setting chooses how the alert before Iqama is presented. The available choices are mute, speech, a sound file, or a sound file with speech.

#### After-time alerts for the other times

When Sunrise, Midnight, or the Last Third is selected, an independent after-time alert setting appears.

This setting chooses the delay after which the alert is issued and the action used to present it.

### Clock

This section contains settings for the Zawali and Ghurubi clocks and settings for automatic clock alerts.

#### Choose clock settings

This option selects the type of clock whose settings you want to customize, either the Zawali clock or the Ghurubi clock. The settings for the selected type then appear.

The Zawali clock is ordinary civil time. The Ghurubi clock starts at sunset: nighttime hours begin at sunset and are followed by daytime hours until the next sunset. It is an Arabic time system that was used historically.

#### Announcement format

This setting chooses the level of detail used when announcing the time. The user can select among the available formats according to the amount of information they prefer to hear.

#### Hour system

This setting chooses whether the time is displayed and announced using the 12-hour or 24-hour system.

#### Announcement representation

This setting chooses whether the time is read in words or digits.

#### Announce seconds

This option includes seconds in the time announcement or limits it to hours and minutes.

#### Announce “zero minutes”

This setting chooses whether the add-on says “zero minutes” when the minute is zero or announces only the hour.

#### Preview announcement

This button lets the user hear the time according to the current clock settings before saving changes.

#### Enabling automatic clock alerts

This option starts or stops alerts for parts of the hour while preserving their settings when disabled.

Alerts can be selected for one or more of the following times:

- Quarter past the hour.
- Half past the hour.
- Three quarters past the hour.
- On the hour.

#### Clock-alert action

This setting chooses how the clock alert is presented. The available options are:

- Speech only.
- Sound file only.
- Sound file and speech.

The add-on includes a default sound file for clock alerts. The user can also choose, preview, or remove a custom sound file.

### Date

This section contains settings for calendars, date-display formats, and daily information.

#### Primary calendar

This setting chooses the calendar that the add-on uses as the primary date when presenting date information. The choices are the Lunar Hijri calendar and the Gregorian calendar.

The Lunar Hijri calendar is the default primary calendar.

#### Include Arabian-calendar information in daily information

This option adds traditional Arabian-calendar information to the astronomical daily information when enabled.

#### Opening the Daily information window

This button opens a window that presents daily information in a form that can be read, reviewed, and copied.

#### Choose the calendar to configure

This setting chooses the calendar whose options you want to customize. Its options appear without affecting the settings of the other calendars.

The add-on includes five calendars:

- Lunar Hijri calendar.
- Gregorian calendar.
- Saudi Solar Hijri calendar.
- Afghan Solar Hijri calendar.
- Persian Solar Hijri calendar.

Only the Lunar Hijri and Gregorian calendars can be selected as the primary calendar. The three solar calendars remain independent additional calendars.

#### Date format

This setting chooses how the selected calendar's date is displayed and announced. Available formats include Double, Full, Moderate, and Short.

#### Lunar Hijri date correction

This option moves the Lunar Hijri date forward or backward by a number of days when needed to match the locally adopted date.

The default is zero, meaning that no correction is applied.

#### Preview announcement

This button lets the user hear a sample date according to the current calendar and settings before saving changes.

The add-on also provides Daily information, which brings together the day's astronomical information and can include traditional Arabian-calendar information when its option is enabled.

### Dhikr alerts

This section controls alerts related to adhkar and the daily Wird, including their times and presentation methods.

#### Enabling dhikr alerts

This is the master switch for dhikr alerts. When it is disabled, every alert in this section stops while its settings are preserved. When it is enabled again, the enabled functions within the section resume working.

Dhikr alerts contain five independent functions: morning adhkar, evening adhkar, the Friday Hour, the daily Wird, and recurring dhikr reminders.

All five functions are disabled by default, and each can be enabled independently.

#### Morning adhkar

The morning-adhkar alert can be scheduled after Fajr, before Sunrise, or after Sunrise, with a number of minutes relative to the chosen time.

The default is fifteen minutes before Sunrise.

#### Evening adhkar

The evening-adhkar alert can be scheduled after Asr, before Maghrib, or after Maghrib, with a number of minutes relative to the chosen time.

The default is fifteen minutes before Maghrib.

#### Friday Hour

This reminder runs on Friday. It can be scheduled after Asr or before Maghrib, with a number of minutes relative to the chosen time.

The default is sixty minutes before Maghrib.

#### Daily Wird

This option sets a fixed time each day for the Wird reminder. The default is 10:00 PM, and the reminder time and text can be changed.

#### Alert action

For morning adhkar, evening adhkar, the Friday Hour, and the daily Wird, one of the following actions can be selected:

- Speech only.
- Sound file only.
- Sound file and speech.

When an action that includes a sound file is selected, options to choose, preview, and remove the file appear.

#### Enabling recurring adhkar

This option starts a recurring reminder that cycles through a number of adhkar. The default interval between reminders is sixty minutes and can be changed according to the user's preference.

Each dhikr within the cycle can be enabled or disabled independently, and each can have its own action.

Two alert methods are available for recurring reminders:

- Speech only.
- Sound file only.

The first reminder begins after the configured interval has fully elapsed. The cycle then moves only among enabled adhkar.

## Shortcut map

The add-on provides several shortcuts that can be changed through NVDA's Input Gestures dialog. They are:

- NVDA+Alt+A: open Awqati settings.
- NVDA+F11: press once to announce details of the current time, twice to announce the previous time, and three times to announce today's prayer times.
- NVDA+Shift+F11: toggle recurring adhkar on or off.
- NVDA+Ctrl+Shift+F11: toggle all automatic alerts on or off.
- NVDA+F12: press once to announce the time, twice to announce the date, and three times to announce daily information.
- NVDA+Shift+F12: repeat the last spoken alert.
- NVDA+Alt+F12: announce alert status.
- NVDA+Shift+P: press once to verify today's prayer times online, and twice to open the Today's prayer times window.
- NVDA+G: press once to announce the Ghurubi time, twice to announce the Qibla direction, and three times to announce the assigned location.
- NVDA+H: press once to announce the Lunar Hijri date, twice to announce the Saudi Solar Hijri date, and three times to announce today's Arabian-calendar summary.
- NVDA+Shift+H: press once to announce the Afghan Solar Hijri date, and twice to announce the Persian Solar Hijri date.
- NVDA+Ctrl+H: press once to announce scientific astronomical daily information, twice to announce Arabian-calendar daily information, and three times to open the Daily information window.

Other commands have no default shortcuts. Shortcuts can be assigned to them through NVDA's Input Gestures dialog.

## Sending feedback

We welcome your comments and suggestions. If you have any comments or suggestions, please contact us by email:

alialomary@gmail.com

## Change log

### Version 4.0.0

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

### Version 3.2

- Changed automatic dhikr reminders from random selection to an ordered cycle.
- Added an interval that can be set in minutes.
- Simplified automatic reminder actions to Speech only or Sound file only.
- Refined interface terminology and standardized announcement formats and shortcuts.

### Version 3.1

- Added automatic dhikr reminders to the Dhikr alerts page.
- Added support for default and custom sound files for each dhikr.
- Improved sound playback and excluded disabled adhkar from reminders.

### Version 3.0

- Added the Dhikr alerts page.
- Added morning and evening adhkar, the Friday Hour reminder, and the daily Wird alert.
- Added custom sounds for dhikr alerts.

### Version 2.1

- Added the Clock page.
- Added Zawali and Ghurubi time.
- Added automatic clock alerts.
- Added multi-press shortcuts for time and date.
- Improved saving of clock and automatic-alert settings.

### Version 1.3

- Improved date formats.
- Fixed Lunar Hijri date correction.
- Added the Syriac month to the full Gregorian format.
