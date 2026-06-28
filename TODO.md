# TODO - Fix scrcpy camera polling interference

## Step 1: Investigate & document current race
- [x] Root-cause analysis report (completed in conversation)

## Step 2: Implement camera session state machine in `ScrcpyManager`
- [ ] Add `CameraState(Enum)`
- [ ] Add a lock protecting `self.processes` and camera state transitions
- [ ] Replace `is_running('camera')` check with `is_camera_available()/is_camera_active()/get_camera_state()` APIs
- [ ] Ensure `list_cameras()` never executes during STARTING/RUNNING/STOPPING/RESTARTING
- [ ] Ensure `start('camera')` transitions STOPPED→STARTING→RUNNING
- [ ] Ensure `stop('camera')` transitions STOPPING, waits for termination, then STOPPED

## Step 3: Update polling logic in `main.py`
- [ ] Prevent `list_cameras()` calls while camera session active/transitioning

## Step 4: Tests
- [ ] Update existing unit tests broken by API changes (e.g. `test_scrcpy_camera_selection`)
- [ ] Add regression tests for simultaneous polling + start/stop/restart and rapid spam
- [ ] Mock external dependencies explicitly (`subprocess.run`, `subprocess.Popen`, etc.) with configured return values
- [ ] Run full unit test suite

## Step 5: Validation
- [ ] Run app build/start smoke test
- [ ] Verify scenarios: camera start/stop, device reconnect, wireless ADB, multiple devices, camera switching, scrcpy restart
- [ ] Check for memory leaks (basic observation) and orphan scrcpy processes

## Step 6: Final report
- [ ] Provide state transition diagram, exact code changes, files modified, test results, remaining risks, confidence.

