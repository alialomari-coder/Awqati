# Windows Location implementation for task 1.2

Awqati uses a neutral `CoordinateProvider` boundary in Application. The
Windows-specific implementation is `WindowsLocationAdapter` in Infrastructure.
Constructing or importing either object performs no location access. A read
starts only when `get_coordinates()` is called explicitly.

## Chosen desktop API

NVDA 2026.2 embeds Python 3.13 on the tested computer, but its runtime does not
include a Python binding for `Windows.Devices.Geolocation`. Adding a new native
runtime dependency solely for location would make packaging and compatibility
less reliable. The adapter therefore calls the inbox desktop COM Location API in
`LocationAPI.dll` directly through Python's bundled `ctypes`.

The one-shot flow creates `ILocation`, calls `RequestPermissions` for
`ILatLongReport`, obtains one report with a bounded wait, reads latitude and
longitude, and releases every COM interface. It does not register
`ILocationEvents`, subscribe to changes, or leave a callback after completion.
The parent window handle is optional at the adapter boundary and can be supplied
by the future UI integration.

Microsoft documents the desktop API and permission call here:

- https://learn.microsoft.com/en-us/windows/win32/api/locationapi/nn-locationapi-ilocation
- https://learn.microsoft.com/en-us/windows/win32/api/locationapi/nf-locationapi-ilocation-requestpermissions
- https://learn.microsoft.com/en-us/windows/win32/api/locationapi/nf-locationapi-ilocation-getreport

Microsoft recommends the newer WinRT API for new Windows applications. The
desktop API is used here because it is present in supported Windows versions and
works without adding an unavailable binding to NVDA's Python package. This
decision can be revisited if NVDA later includes a tested WinRT binding.

## Threading and privacy

`get_coordinates()` and the subsequent spatial scan are synchronous and must
be invoked by the NVDA adapter on a worker thread. No task 1.2 product UI or
gesture calls them. Permission remains explicit, the report wait is bounded, and
there is no busy wait. Awqati does not use IP location, civic-address reverse
geocoding, HTTP, or any endpoint in this flow. The returned coordinates are
matched only against the bundled spatial index.

The adapter maps permission denial, platform unavailability, timeout, API
failure, and invalid coordinates to neutral typed failures. `LocationService`
keeps an already assigned location when any attempt fails.
