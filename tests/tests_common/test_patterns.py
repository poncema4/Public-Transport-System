from unittest.mock import MagicMock

from common.patterns import CommandExecutor
from server.server import Observer, Subject


def test_subject_register_and_notify_observer():
    subject = Subject()
    observer = MagicMock(spec=Observer)

    subject.register_observer(observer)

    assert observer in subject._observers

    subject.notify_observers(event="test_event")

    observer.update.assert_called_once_with(subject, event="test_event")

def test_subject_remove_observer():
    subject = Subject()
    observer = MagicMock(spec=Observer)

    subject.register_observer(observer)
    subject.remove_observer(observer)

    assert observer not in subject._observers

    subject.notify_observers(event="test_event")

    observer.update.assert_not_called()

def test_subject_does_not_register_same_observer_twice():
    subject = Subject()
    observer = MagicMock(spec=Observer)

    subject.register_observer(observer)
    subject.register_observer(observer)  # should not duplicate

    assert subject._observers.count(observer) == 1

def test_command_executor_execute_is_stub():
    executor = CommandExecutor()
    assert hasattr(executor, "execute")
    executor.execute("ANY_COMMAND", {"some_param": 1})
