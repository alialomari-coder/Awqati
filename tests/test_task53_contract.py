from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Task53ContractTests(unittest.TestCase):
	def test_commands_and_buttons_share_context_actions(self):
		plugin = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py").read_text(encoding="utf-8")
		panel = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/settings_panel.py").read_text(encoding="utf-8")
		self.assertIn("verify_prayer_times=self._actions.verify_online", plugin)
		self.assertIn("self._actions.copy_diagnostics()", plugin)
		self.assertIn("check_data_updates=self._actions.check_data_updates", plugin)
		self.assertIn("self._actions.verify_online(from_global_command=True)", plugin)
		self.assertIn("self._context.check_data_updates()", plugin)
		self.assertIn('label=_(\"Copy diagnostic information\")', panel)
		self.assertIn('label=_(\"Check for data updates\")', panel)
		self.assertIn("Verify today's prayer times online...", panel)
		self.assertIn("context.copy_diagnostics()", panel)
		self.assertIn("context.check_data_updates()", panel)
		self.assertIn("context.verify_prayer_times()", panel)
		verification_script = plugin[plugin.index("def script_prayerVerification"):plugin.index("def script_gregorianDate")]
		update_script = plugin[plugin.index("def script_dataUpdates"):plugin.index("def terminate")]
		self.assertIn("self._actions.verify_online(from_global_command=True)", verification_script)
		self.assertNotIn("self._actions.check_data_updates", update_script)

	def test_global_command_privacy_prompt_uses_nvda_popup_lifecycle(self):
		source = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/task53_actions.py").read_text(encoding="utf-8")
		method = source[source.index("def verify_online"):source.index("def _run_async")]
		self.assertIn("from_global_command: bool = False", method)
		self.assertIn("wx.CallLater(100, ui.message, privacy_message)", method)
		self.assertEqual(method.count("wx.MessageBox("), 1)
		self.assertLess(method.index("gui.mainFrame.prePopup()"), method.index("wx.MessageBox("))
		self.assertLess(method.index("wx.MessageBox("), method.index("gui.mainFrame.postPopup()"))
		self.assertIn("finally:", method)

	def test_opening_settings_and_composition_do_not_start_network(self):
		plugin = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py").read_text(encoding="utf-8")
		compose = plugin[plugin.index("def _compose"):plugin.index("def _language")]
		self.assertNotIn(".check(", compose)
		self.assertNotIn(".verify(", compose)
		panel = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/settings_panel.py").read_text(encoding="utf-8")
		make = panel[panel.index("def makeSettings"):panel.index("def _register")]
		self.assertNotIn("verify_prayer_times()", make)
		self.assertIn("Bind(wx.EVT_BUTTON", make)
		self.assertNotIn("self.data_updates.check(", make)

	def test_production_data_channel_is_public_https_and_wired_outside_domain(self):
		plugin = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/plugin.py").read_text(encoding="utf-8")
		self.assertIn(
			"https://raw.githubusercontent.com/alialomari-coder/awqati-data/main/manifest.json",
			plugin,
		)
		self.assertIn("DATA_UPDATE_MANIFEST_URL,", plugin)
		for path in (ROOT / "addon/globalPlugins/awqati/domain").glob("*.py"):
			self.assertNotIn("awqati-data", path.read_text(encoding="utf-8"), path.name)

	def test_privacy_prompt_precedes_worker_and_is_session_only(self):
		source = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/task53_actions.py").read_text(encoding="utf-8")
		start = source.index("def verify_online")
		end = source.index("def _run_async")
		method = source[start:end]
		self.assertLess(method.index("wx.MessageBox"), method.index("self._run_async"))
		self.assertIn("self._privacy_approved = True", method)
		self.assertNotIn("save", method.lower())

	def test_explicit_network_operations_never_use_an_app_modal_progress_dialog(self):
		source = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/task53_actions.py").read_text(encoding="utf-8")
		self.assertNotIn("wx.ProgressDialog", source)
		self.assertNotIn("wx.PD_APP_MODAL", source)
		self.assertNotIn("ShowModal", source[source.index("class _OperationDialog"):])
		async_method = source[source.index("def _run_async"):source.index("def _verification_success")]
		self.assertIn("wx.CallLater(100, ui.message, message)", async_method)
		self.assertIn("wx.CallLater(100, complete)", async_method)
		self.assertLess(async_method.index("dialog.cancel_button.SetFocus()"),
			async_method.index("wx.CallLater(100, ui.message, message)"))
		self.assertLess(async_method.index("dialog.Destroy()"),
			async_method.index("wx.CallLater(100, complete)"))
		self.assertIn("parent or _interaction_parent()", async_method)
		self.assertIn("target=run", async_method)
		self.assertIn('name="Awqati explicit network operation"', async_method)
		self.assertIn("(DataUpdateError, OnlinePrayerVerificationError, OSError)", async_method)
		self.assertIn("logHandler.log.warning", async_method)

	def test_aladhan_preparation_and_request_run_inside_the_background_worker(self):
		source = (ROOT / "addon/globalPlugins/awqati/nvda_adapter/task53_actions.py").read_text(encoding="utf-8")
		start = source.index("def verify_online")
		end = source.index("def _run_async")
		method = source[start:end]
		worker_start = method.index("def verify(token: CancellationToken)")
		run_start = method.index("self._run_async")
		self.assertGreater(method.index("self.zones.get_timezone"), worker_start)
		self.assertGreater(method.index("self.prayers.calculate"), worker_start)
		self.assertLess(method.index("self.online_verifier.verify"), run_start)
		self.assertIn("token.raise_if_cancelled()", method)

	def test_domain_has_no_network_or_platform_dependencies(self):
		for path in (ROOT / "addon/globalPlugins/awqati/domain").glob("*.py"):
			source = path.read_text(encoding="utf-8")
			for forbidden in ("urllib", "socket", "wx", "globalPluginHandler", "AlAdhan"):
				self.assertNotIn(forbidden, source, path.name)

	def test_help_no_longer_claims_task53_is_unimplemented(self):
		for relative in ("addon/doc/ar/readme.html", "addon/doc/en/readme.html"):
			source = (ROOT / relative).read_text(encoding="utf-8")
			self.assertNotIn("غير منفذين بعد", source)
			self.assertNotIn("remain placeholders", source)
