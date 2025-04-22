# Observer pattern
class Observer:
    def update(self, subject, *args, **kwargs):
        pass

class Subject:
    def __init__(self):
        self._observers = []

    def register_observer(self, observer):
        if observer not in self._observers:
            self._observers.append(observer)

    def remove_observer(self, observer):
        if observer in self._observers:
            self._observers.remove(observer)

    def notify_observers(self, *args, **kwargs):
        for observer in self._observers:
            observer.update(self, *args, **kwargs)

# Command pattern
class CommandExecutor:
    def execute(self, command, params=None):
        pass