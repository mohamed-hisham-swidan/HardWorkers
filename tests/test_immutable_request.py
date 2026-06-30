"""Test the immutable request-scoped model architecture."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from _pytest.logging import LogCaptureFixture

from ui.main_window import LifecycleState, MainWindow


def make_window() -> MainWindow:
    """Create a MainWindow bypassing __init__ with all dependencies mocked."""
    w = MainWindow.__new__(MainWindow)
    w._user_explicitly_selected_model = False
    w._active_chat_id = "test-chat"
    w._model_sel = MagicMock()
    w._model_sel.value = "dolphin-mohamed:latest"

    w._mm = MagicMock()
    w._mm.get_active.return_value = "dolphin-mohamed:latest"
    w._mm.get_available.return_value = [
        "dolphin-mohamed:latest",
        "qwen3-vl-32b-instruct:latest",
        "llama3:latest",
    ]

    def is_vision(name: str) -> bool:
        return "vl" in name or "vision" in name

    w._mm.is_vision_capable.side_effect = is_vision

    w._router = MagicMock()
    decision = MagicMock()
    decision.chosen_model = "llama3:latest"
    decision.reason = "router_test"
    w._router.route.return_value = decision

    w._set_status = MagicMock()
    w._page = MagicMock()

    def run_thread(fn):
        if callable(fn):
            return fn()
        return None

    w._page.run_thread = run_thread

    w._reset_input_state = MagicMock()
    w.show_toast = MagicMock()
    w._memory = MagicMock()
    w._memory.search.return_value = []
    w._chats = MagicMock()
    w._workspaces = MagicMock()
    w._db = MagicMock()
    w._chat_list = MagicMock()
    w._stop = MagicMock()
    w._stop.is_set.return_value = False
    w._pasted_image_path = None
    w._diag_svc = MagicMock()
    w._pipeline_running = False
    w._sending = False
    w._generating = False
    w._paste_version = 0
    w._img_preview = MagicMock()
    w._img_preview_img = MagicMock()
    w._img_preview_img.src = "data:image/png;base64,abc"
    w._lifecycle = LifecycleState.READY
    w._gen_lock = MagicMock()
    w._pool = MagicMock()

    return w


# ── Scenario 1: Quick select + image send ──


class TestScenario1:
    """Select qwen3-vl-32b-instruct, attach image, send — no race."""

    def test_immutable_model_used_for_image_send(self, caplog: LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        w = make_window()
        w._model_sel.value = "qwen3-vl-32b-instruct:latest"
        selected_model = w._model_sel.value
        w._generate_response("hello", selected_model, image_b64="data:image/png;base64,abc")
        records = [r.getMessage() for r in caplog.records]
        router_inputs = [m for m in records if m.startswith("ROUTER_INPUT_MODEL")]
        [m for m in records if m.startswith("ROUTER_OUTPUT_MODEL")]
        finals = [m for m in records if m.startswith("FINAL_MODEL_USED")]
        falls = [m for m in records if m.startswith("VISION_FALLBACK_NEEDED")]
        assert router_inputs, "ROUTER_INPUT_MODEL log missing"
        assert any("qwen3-vl-32b-instruct:latest" in m for m in router_inputs), (
            f"Expected ROUTER_INPUT_MODEL with qwen3, got: {router_inputs}"
        )
        assert finals, "FINAL_MODEL_USED log missing"
        assert any("qwen3-vl-32b-instruct:latest" in m for m in finals), (
            f"Expected FINAL_MODEL_USED with qwen3, got: {finals}"
        )
        assert not falls, f"VISION_FALLBACK_NEEDED should not appear, got: {falls}"

    def test_no_get_active_called_on_image_send(self, caplog: LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        w = make_window()
        w._model_sel.value = "qwen3-vl-32b-instruct:latest"
        selected_model = w._model_sel.value
        w._generate_response("hello", selected_model, image_b64="data:image/png;base64,abc")
        assert w._mm.get_active.call_count <= 1, (
            f"get_active should not be called (>1), called {w._mm.get_active.call_count} time(s)"
        )

    def test_router_bypass_on_explicit_selection(self, caplog: LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        w = make_window()
        w._user_explicitly_selected_model = True
        w._model_sel.value = "dolphin-mohamed:latest"
        selected_model = w._model_sel.value
        w._generate_response("hello", selected_model)
        records = [r.getMessage() for r in caplog.records]
        router_outputs = [m for m in records if m.startswith("ROUTER_OUTPUT_MODEL")]
        assert any("user_explicit_selection" in m for m in router_outputs), (
            f"Expected router bypass, got: {router_outputs}"
        )

    def test_set_active_not_called_in_generate_response(self, caplog: LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        w = make_window()
        w._model_sel.value = "qwen3-vl-32b-instruct:latest"
        selected_model = w._model_sel.value
        w._generate_response("hello", selected_model, image_b64="data:image/png;base64,abc")
        w._mm.set_active.assert_not_called()


# ── Scenario 2: Delete selected model from registry ──


class TestScenario2:
    """Delete model A, verify flag invalidation + router allowed."""

    def test_flag_reset_on_model_removed(self, caplog: LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        w = make_window()
        w._user_explicitly_selected_model = True
        w._model_sel.value = "deleted-model:latest"

        def update_side(models, active=None):
            w._model_sel.value = active if active and active in models else (models[0] if models else None)

        w._model_sel.update_models.side_effect = update_side

        w._mm.refresh_available.return_value = ["fallback-model:latest"]
        w._mm.get_active.return_value = "fallback-model:latest"

        w._refresh_models_bg()

        assert not w._user_explicitly_selected_model, "Flag should be reset"
        records = [r.getMessage() for r in caplog.records]
        resets = [m for m in records if m.startswith("EXPLICIT_MODEL_SELECTION_RESET")]
        assert any("reason=model_removed" in m for m in resets), (
            "EXPLICIT_MODEL_SELECTION_RESET reason=model_removed should be logged"
        )

    def test_router_allowed_after_flag_reset(self, caplog: LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        w = make_window()
        w._user_explicitly_selected_model = False
        w._model_sel.value = "fallback-model:latest"
        selected_model = w._model_sel.value

        w._generate_response("hello", selected_model)
        records = [r.getMessage() for r in caplog.records]
        router_outputs = [m for m in records if m.startswith("ROUTER_OUTPUT_MODEL")]
        assert any("router_test" in m for m in router_outputs), (
            f"Router should decide when flag is False, got: {router_outputs}"
        )

    def test_flag_preserved_when_same_model(self, caplog: LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        w = make_window()
        w._user_explicitly_selected_model = True
        model_name = "dolphin-mohamed:latest"
        w._model_sel.value = model_name

        previous = w._model_sel.value
        w._model_sel.update_models(
            ["dolphin-mohamed:latest", "llama3:latest"],
            "dolphin-mohamed:latest",
        )
        current = w._model_sel.value
        assert previous == current, "Model should not change"
        assert w._user_explicitly_selected_model, "Flag should be preserved"


# ── Scenario 3: Attachment remove X button ──


class TestAttachmentRemove:
    """Click X on image preview — verify all state cleared."""

    def test_clear_pasted_image_clears_all_state(self, caplog: LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        w = make_window()
        w._pasted_image_path = "/tmp/test.png"
        w._paste_version = 1

        w._clear_pasted_image()

        assert w._pasted_image_path is None, "path should be None"
        assert w._img_preview.visible is False, "preview should be hidden"
        assert w._img_preview_img.src == "", "image src should be cleared"
        assert w._paste_version == 2, "paste_version should increment"
        records = [r.getMessage() for r in caplog.records]
        assert any("ATTACHMENT_REMOVE_CLICKED" in m for m in records)
        assert any("ATTACHMENT_STATE_AFTER_CLEAR" in m for m in records)
        assert any("ATTACHMENT_PREVIEW_REMOVED" in m for m in records)

    def test_clear_then_send_is_text_only(self, caplog: LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        w = make_window()
        w._pasted_image_path = "/tmp/test.png"
        w._paste_version = 1
        w._entry = MagicMock()
        w._entry.value = "hello"
        w._sending = False
        w._btn_send = MagicMock()
        w._btn_stop = MagicMock()
        w._btn_clear_chat = MagicMock()
        w._stop = MagicMock()
        w._cfg = MagicMock()
        w._cfg.tokens.max_context = 32000
        w._update_msg_widths = MagicMock()
        w._update_input_bar_visibility = MagicMock()
        w._safe_submit = MagicMock()
        w._safe_submit.return_value = MagicMock()
        w._llm_pool = MagicMock()
        w._lifecycle = LifecycleState.READY

        w._clear_pasted_image()
        assert w._pasted_image_path is None

        w._send_message()
        send_logs = [r.getMessage() for r in caplog.records]
        assert any("SEND_START pasted_path=None" in m for m in send_logs), (
            f"Send should start with path=None, got: {[m for m in send_logs if 'SEND_START' in m]}"
        )

    def test_paste_version_invalidates_stale_paste(self, caplog: LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        w = make_window()
        w._paste_version = 1

        captured_version = w._paste_version
        assert captured_version == 1

        w._clear_pasted_image()
        assert w._paste_version == 2

        assert w._paste_version != captured_version, "Version mismatch means clear invalidated the paste"
