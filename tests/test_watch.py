from screenmatch.watch import ScreenWatch


def test_debounce_waits_for_stable_content_then_fires_once():
    watch = ScreenWatch(stable_s=4)
    assert watch.observe("a", "A", 0) is None
    assert watch.observe("a", "A", 3) is None
    assert watch.observe("a", "A", 4) == "A"
    assert watch.complete() is None
    assert watch.observe("a", "A", 9) is None
    assert watch.observe("b", "B", 10) is None
    assert watch.observe("b", "B", 12) is None
    assert watch.observe("a", "A", 13) is None
    assert watch.observe("a", "A", 16) is None
    assert watch.observe("a", "A", 17) == "A"


def test_selection_release_queries_immediately():
    watch = ScreenWatch(stable_s=4)
    watch.arm_immediate()
    assert watch.observe("a", "A", 0) == "A"


def test_pause_blocks_immediate_query_until_resume():
    watch = ScreenWatch(stable_s=4)
    watch.arm_immediate()
    watch.pause()
    assert watch.observe("a", "A", 0) is None
    watch.resume()
    assert watch.observe("a", "A", 1) == "A"


def test_changes_while_busy_do_not_overlap_and_only_latest_stable_follows():
    watch = ScreenWatch(stable_s=4)
    watch.arm_immediate()
    assert watch.observe("a", "A", 0) == "A"
    assert watch.busy
    now = 0
    for index in range(20):
        now += 1
        assert watch.observe(f"flicker-{index}", f"F{index}", now) is None
        assert watch.busy
    assert watch.observe("z", "Z", now) is None
    assert watch.observe("z", "Z", now + 4) is None
    assert watch.busy
    assert watch.complete() == "Z"
    assert watch.busy
    assert watch.complete() is None
    assert watch.busy is False


def test_pause_drops_the_queued_follow_up():
    watch = ScreenWatch(stable_s=4)
    watch.arm_immediate()
    assert watch.observe("a", "A", 0) == "A"
    assert watch.observe("b", "B", 1) is None
    assert watch.observe("b", "B", 5) is None
    watch.pause()
    assert watch.complete() is None
    assert watch.busy is False
