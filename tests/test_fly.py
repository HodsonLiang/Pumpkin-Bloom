import queue
import unittest
from unittest.mock import Mock, patch
from pikmin.fly_engine import Route, Controller, distance, advance


class RouteTests(unittest.TestCase):
    def route(self):
        r = Route()
        r.position = (0., 0.)
        r.add((0., .001))
        r.speed, r.interval, r.dwell = 36., 2., 3.
        return r

    def test_speed_and_cadence(self):
        r = self.route()
        send = Mock()
        r.start()
        r.tick(1, send)
        send.assert_not_called()
        r.tick(1, send)
        self.assertEqual(send.call_count, 1)
        self.assertAlmostEqual(distance((0, 0), r.position), 20, places=4)

    def test_eta_includes_quantized_steps_and_dwell(self):
        r = self.route()
        r.add((0, .002))
        self.assertEqual(r.remaining()[1], 27)  # 6 steps each segment + 3s dwell
        r.start()
        r.tick(1, Mock())
        self.assertEqual(r.remaining()[1], 26)

    def test_pause_freezes_eta_and_position(self):
        r = self.route()
        r.start()
        r.tick(1, Mock())
        r.running = False
        before = (r.position, r.remaining())
        send = Mock()
        r.tick(100, send)
        send.assert_not_called()
        self.assertEqual(before, (r.position, r.remaining()))

    def test_clear_holds_position_and_does_not_restart(self):
        r = self.route()
        r.start()
        r.tick(2, Mock())
        before = r.position
        r.clear()
        r.add((0, .002))
        send = Mock()
        r.tick(100, send)
        send.assert_not_called()
        self.assertEqual(before, r.position)
        self.assertFalse(r.running)

    def test_ids_never_reused(self):
        r = self.route()
        r.arrive()
        r.add((0, .002))
        self.assertEqual([uid for uid, _ in r.points], [1, 2])
        r.clear()
        r.add((0, .003))
        self.assertEqual(r.points[0][0], 3)

    def test_loop_preserves_route_and_returns_to_first_point(self):
        r = self.route()
        r.add((0, .002))
        r.loop = True
        r.position = r.points[-1][1]
        r.index = 1
        r.start()
        r.tick(2, Mock())
        self.assertEqual((r.index, r.laps, r.running), (0, 1, True))
        self.assertEqual(len(r.points), 2)
        send = Mock()
        r.tick(3, send)
        send.assert_not_called()
        r.tick(2, send)
        self.assertLess(r.position[1], .002)

    def test_finish_stops_at_exact_endpoint(self):
        r = self.route()
        r.start()
        for _ in range(6):
            r.tick(2, Mock())
        self.assertEqual(r.position, (0, .001))
        self.assertFalse(r.running)
        self.assertEqual(r.remaining(), (0, 0))

    def test_failed_dispatch_does_not_advance(self):
        r = self.route()
        r.start()
        with self.assertRaises(OSError):
            r.tick(2, Mock(side_effect=OSError('device unavailable')))
        self.assertEqual(r.position, (0, 0))

    def test_date_line_uses_short_route(self):
        a, b = (0, 179.99), (0, -179.99)
        self.assertLess(distance(a, b), 2300)
        mid = advance(a, b, distance(a, b)/2)
        self.assertAlmostEqual(abs(mid[1]), 180, places=5)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.c = Controller(queue.Queue(), queue.Queue())
        self.c.device = Mock()

    def test_clear_does_not_release_or_reset_location(self):
        self.c.command('add', [(25, 121)])
        self.c.command('start', None)
        position = self.c.route.position
        self.c.command('clear', None)
        self.c.device.reset.assert_not_called()
        self.c.device.release.assert_not_called()
        self.assertEqual(self.c.route.position, position)
        self.assertEqual(self.c.route.points, [])

    def test_live_settings_change_step_size_and_cadence(self):
        self.c.route.position = (0, 0)
        self.c.command('add', [(0, .01)])
        self.c.command('start', None)
        self.c.route.tick(1, self.c.device.send)
        self.c.command('settings', (72., .5, 0., True))
        self.c.route.tick(.5, self.c.device.send)
        self.assertAlmostEqual(distance((0, 0), self.c.route.position), 10, places=4)
        self.assertTrue(self.c.route.running)

    def test_invalid_settings_leave_previous_values(self):
        with self.assertRaises(ValueError):
            self.c.command('settings', (float('nan'), 0, 8, False))
        self.assertEqual(self.c.route.speed, 18)

    def test_close_failure_still_ends_worker(self):
        self.c.device.reset.side_effect = OSError('offline')
        with self.assertRaises(OSError):
            self.c.command('close', None)
        self.assertTrue(self.c.closed)


if __name__ == '__main__':
    unittest.main()
