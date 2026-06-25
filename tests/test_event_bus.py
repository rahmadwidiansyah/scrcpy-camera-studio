import os
import sys
import unittest
from dataclasses import dataclass

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.event_bus import EventBus

@dataclass
class DummyEvent:
    message: str

@dataclass
class AnotherEvent:
    value: int

class TestEventBus(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()

    def test_subscribe_and_publish(self):
        received_events = []
        
        def listener(event):
            received_events.append(event)
            
        self.bus.subscribe(DummyEvent, listener)
        
        event = DummyEvent(message="Hello World")
        self.bus.publish(event)
        
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0].message, "Hello World")

    def test_unsubscribe(self):
        received_events = []
        
        def listener(event):
            received_events.append(event)
            
        self.bus.subscribe(DummyEvent, listener)
        self.bus.publish(DummyEvent(message="First"))
        
        self.bus.unsubscribe(DummyEvent, listener)
        self.bus.publish(DummyEvent(message="Second"))
        
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0].message, "First")

    def test_multiple_subscribers(self):
        results = []
        
        self.bus.subscribe(DummyEvent, lambda e: results.append(f"L1: {e.message}"))
        self.bus.subscribe(DummyEvent, lambda e: results.append(f"L2: {e.message}"))
        
        self.bus.publish(DummyEvent(message="Broadcast"))
        
        self.assertEqual(len(results), 2)
        self.assertIn("L1: Broadcast", results)
        self.assertIn("L2: Broadcast", results)

    def test_unrelated_events_not_triggered(self):
        dummy_received = []
        another_received = []
        
        self.bus.subscribe(DummyEvent, lambda e: dummy_received.append(e))
        self.bus.subscribe(AnotherEvent, lambda e: another_received.append(e))
        
        self.bus.publish(AnotherEvent(value=42))
        
        self.assertEqual(len(dummy_received), 0)
        self.assertEqual(len(another_received), 1)
        self.assertEqual(another_received[0].value, 42)

    def test_listener_error_handling(self):
        results = []
        
        def failing_listener(e):
            raise RuntimeError("Something went wrong")
            
        def working_listener(e):
            results.append(e.message)
            
        self.bus.subscribe(DummyEvent, failing_listener)
        self.bus.subscribe(DummyEvent, working_listener)
        
        # This publish should not raise an exception even though the first listener fails
        try:
            self.bus.publish(DummyEvent(message="NoBlock"))
        except Exception as err:
            self.fail(f"Publish raised unexpected exception: {err}")
            
        # The working listener should still run
        self.assertEqual(results, ["NoBlock"])


if __name__ == "__main__":
    unittest.main()
