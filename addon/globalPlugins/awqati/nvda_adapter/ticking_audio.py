"""One persistent low-priority worker and WavePlayer for all ticking requests.

The two tiny WAVs are cached once. A single pending slot replaces older work;
there is no per-click thread, disk access or backlog. Only the main NVDA
thread requests/cancels sound; the worker never touches timer state or wx.
"""
from pathlib import Path
import threading
import wave


class TickingAudio:
    def __init__(self, folder, player_factory, diagnostic=lambda error: None):
        self.folder, self.factory, self.diagnostic = Path(folder), player_factory, diagnostic
        self.condition = threading.Condition()
        self.thread, self.player, self.request = None, None, None
        self.closed, self.generation = False, 0
        self.playing = False

    def play(self, index):
        with self.condition:
            if self.closed:
                return
            self.request = (index, self.generation)
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name="AwqatiClockTicking", daemon=True)
                self.thread.start()
            self.condition.notify()

    def cancel(self):
        with self.condition:
            self.generation += 1
            active = self.playing or self.request is not None
            self.request = None
            player = self.player if active else None
        if player:
            try:
                player.stop()
            except Exception as error:
                self.diagnostic(error)

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify()
        self.cancel()  # No join on NVDA's main thread.

    def _run(self):
        player = None
        try:
            clips = []
            params = None
            for name in ("tick", "tock"):
                with wave.open(str(self.folder / (name + ".wav")), "rb") as source:
                    current = source.getparams()[:3]
                    if params is not None and current != params:
                        raise ValueError("tick WAV formats differ")
                    params = current
                    if player is None:
                        player = self.factory(source)
                    clips.append(source.readframes(source.getnframes()))
            with self.condition:
                if self.closed:
                    return
                self.player = player
            while True:
                with self.condition:
                    self.condition.wait_for(lambda: self.closed or self.request is not None)
                    if self.closed:
                        return
                    index, generation = self.request
                    self.request = None
                    self.playing = True
                try:
                    if generation != self.generation:
                        continue
                    player.feed(clips[index])
                    if generation != self.generation:
                        player.stop()
                    else:
                        player.idle()
                finally:
                    with self.condition:
                        self.playing = False
        except Exception as error:
            self.diagnostic(error)
        finally:
            if player:
                try:
                    player.close()
                except Exception as error:
                    self.diagnostic(error)
            with self.condition:
                self.player, self.request, self.playing = None, None, False
                # Fail quietly for this session, without repeated worker creation.
                self.closed = True
