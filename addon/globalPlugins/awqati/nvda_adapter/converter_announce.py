"""Optional NVDA announcement boundary shared by converter dialogs."""
def _nvda_announce(text):
	try:
		import ui
		ui.message(text)
	except ImportError:
		# Standalone launcher has native value events, without a second speech API.
		pass

