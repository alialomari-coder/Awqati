"""One interruptible NVDA sequence with explicit utterance boundaries per item."""


class DaySpeech:
    def __init__(self):
        self.busy = False
        self.generation = 0
        self.listener = None

    def speak(self, lines):
        import speech
        from speech.commands import CallbackCommand, EndUtteranceCommand
        from speech.extensions import speechCanceled
        self.stop()
        self.generation += 1
        generation = self.generation
        self.busy = True
        def finished():
            if generation != self.generation:
                return
            self.busy = False
            if self.listener is not None:
                speechCanceled.unregister(self.listener)
                self.listener = None
        self.listener = finished
        speechCanceled.register(finished)
        sequence = []
        for line in lines:
            sequence.extend((line, EndUtteranceCommand()))
        # Keep the completion callback in the last spoken utterance. An
        # index-only trailing utterance can stall some synthesizers.
        if sequence:
            sequence.pop()
        sequence.append(CallbackCommand(finished, name="Awqati On This Day complete"))
        try:
            speech.speak(sequence)
        except Exception:
            finished()
            raise

    def stop(self):
        if not self.busy:
            return
        import speech
        from speech.extensions import speechCanceled
        self.generation += 1
        self.busy = False
        if self.listener is not None:
            speechCanceled.unregister(self.listener)
            self.listener = None
        speech.cancelSpeech()
