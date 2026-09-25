"""Tests for the WebAppKit command-line tools."""

import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import imfusion
import numpy as np
import pytest

from imfusion_webappkit import Workflow
from imfusion_webappkit.cli import (
    AVAILABLE_TEMPLATES,
    CheckResult,
    build_parser,
    run_demo,
    run_doctor,
    run_record,
    scaffold_simple_project,
    scaffold_project,
)
from imfusion_webappkit.static_demo import StaticDemoSpec
from imfusion_webappkit.static_demo.build import load_spec


def _relative_paths(paths, root):
    return {path.relative_to(root).as_posix() for path in paths}


def test_package_import_is_lightweight_for_doctor():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import imfusion_webappkit; "
                "assert 'imfusion' not in sys.modules"
            ),
        ],
        check=False,
    )
    assert completed.returncode == 0


def test_init_help_lists_available_templates(capsys):
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["init", "--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "Available templates:" in output
    assert "simple" in output
    assert "Threshold-segmentation action" in output
    assert "workflow" in output
    assert "monai" in output
    assert "--theme" in output
    assert "dark" in output
    assert "gray" in output
    assert "light" in output


def test_doctor_reports_results_and_fails_for_failed_check(capsys):
    checks = [
        lambda: CheckResult("ok", "Working", "ready"),
        lambda: CheckResult("fail", "Broken", "not ready", "Fix it."),
    ]

    assert run_doctor(checks=checks) == 1
    output = capsys.readouterr().out
    assert "[ok] Working: ready" in output
    assert "[fail] Broken: not ready" in output
    assert "Hint: Fix it." in output
    assert "1 check(s) failed." in output


def test_simple_scaffold_replaces_project_metadata(tmp_path):
    destination = tmp_path / "spine-segmentation"

    written = scaffold_simple_project(
        destination,
        title="Spine Segmentation",
    )

    assert _relative_paths(written, destination) == {
        ".claude/skills/work-with-imfusion-images/SKILL.md",
        ".cursor/skills/work-with-imfusion-images/SKILL.md",
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "algorithm.py",
        "app.py",
        "pyproject.toml",
    }
    generated_pyproject = (destination / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "spine-segmentation"' in generated_pyproject
    assert "imfusion-webappkit = { path =" in generated_pyproject
    assert "{{WEBAPPKIT_SOURCE_LINE}}" not in generated_pyproject
    app_source = (destination / "app.py").read_text(encoding="utf-8")
    algorithm_source = (destination / "algorithm.py").read_text(encoding="utf-8")
    assert 'title="Spine Segmentation"' in app_source
    assert "ThemePreset.DARK" in app_source
    assert '"threshold"' in app_source
    assert '"gain"' not in app_source
    assert "Data.Modality.LABEL" in algorithm_source
    compile(app_source, str(destination / "app.py"), "exec")
    compile(
        algorithm_source,
        str(destination / "algorithm.py"),
        "exec",
    )
    completed = subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=destination,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    spec = importlib.util.spec_from_file_location(
        "generated_simple_algorithm",
        destination / "algorithm.py",
    )
    assert spec is not None and spec.loader is not None
    algorithm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(algorithm)
    images = imfusion.SharedImageSet(np.array([[[[0], [200]]]], dtype=np.float32))
    result = algorithm.process_image(
        images,
        threshold=100,
        app=SimpleNamespace(update_progress=lambda *_args: None),
    )
    np.testing.assert_array_equal(
        np.asarray(result[0]),
        np.array([[0], [1]], dtype=np.uint8),
    )
    assert result.modality == imfusion.Data.Modality.LABEL


def test_scaffold_refuses_to_overwrite_known_files(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    existing = destination / "app.py"
    existing.write_text("keep me", encoding="utf-8")

    with pytest.raises(FileExistsError, match="app.py"):
        scaffold_simple_project(destination)

    assert existing.read_text(encoding="utf-8") == "keep me"


def test_scaffold_refuses_to_overwrite_agent_guidance(tmp_path):
    destination = tmp_path / "existing-guidance"
    existing = destination / ".cursor" / "skills" / "work-with-imfusion-images"
    existing.mkdir(parents=True)
    skill = existing / "SKILL.md"
    skill.write_text("keep me", encoding="utf-8")

    with pytest.raises(FileExistsError, match="work-with-imfusion-images"):
        scaffold_simple_project(destination)

    assert skill.read_text(encoding="utf-8") == "keep me"


def test_workflow_scaffold_contains_guided_processing_steps(tmp_path):
    destination = tmp_path / "guided-demo"

    written = scaffold_project(
        destination,
        template="workflow",
        title="Guided Demo",
    )

    assert _relative_paths(written, destination) == {
        ".claude/skills/work-with-imfusion-images/SKILL.md",
        ".cursor/skills/work-with-imfusion-images/SKILL.md",
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "algorithm.py",
        "app.py",
        "pyproject.toml",
    }
    app_source = (destination / "app.py").read_text(encoding="utf-8")
    assert 'title="Guided Demo"' in app_source
    assert "ThemePreset.DARK" in app_source
    assert "ParameterStep(" in app_source
    assert "ProcessingStep(" in app_source
    assert "BrushStep(" in app_source
    assert "ValidationStep(" in app_source
    assert "ExportStep(" in app_source
    compile(app_source, str(destination / "app.py"), "exec")
    completed = subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=destination,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_monai_scaffold_contains_cached_direct_inference(tmp_path):
    destination = tmp_path / "monai-demo"

    written = scaffold_project(
        destination,
        template="monai",
        title="MONAI Demo",
    )

    assert "monai" in AVAILABLE_TEMPLATES
    assert _relative_paths(written, destination) == {
        ".claude/skills/integrate-monai-model/SKILL.md",
        ".claude/skills/work-with-imfusion-images/SKILL.md",
        ".cursor/skills/integrate-monai-model/SKILL.md",
        ".cursor/skills/work-with-imfusion-images/SKILL.md",
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "algorithm.py",
        "app.py",
        "pyproject.toml",
    }
    app_source = (destination / "app.py").read_text(encoding="utf-8")
    algorithm_source = (destination / "algorithm.py").read_text(encoding="utf-8")
    pyproject = (destination / "pyproject.toml").read_text(encoding="utf-8")
    readme = (destination / "README.md").read_text(encoding="utf-8")
    agent_guidance = (destination / "AGENTS.md").read_text(encoding="utf-8")
    monai_skill = (
        destination / ".cursor" / "skills" / "integrate-monai-model" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert 'title="MONAI Demo"' in app_source
    assert "ThemePreset.DARK" in app_source
    assert "InputSelectionStep(" in app_source
    assert 'inputs_from="select_input"' in app_source
    assert "ProcessingStep(" in app_source
    assert "auto_run=False" in app_source
    assert 'run_label="Run Segmentation"' in app_source
    assert "monai>=1.4" in pyproject
    assert "huggingface-hub>=0.24" in pyproject
    assert "torch>=2.4" in pyproject
    assert "image.numpy()" in algorithm_source
    assert "sliding_window_inference(" in algorithm_source
    assert "SpatialResample" in algorithm_source
    assert "Invertd" not in algorithm_source
    assert "torch.hub.get_dir()" in algorithm_source
    assert "ConfigParser" in algorithm_source
    assert "model.load_state_dict(" in algorithm_source
    assert "SupervisedEvaluator" not in algorithm_source
    assert "automatically downloads the configured bundle" in readme
    assert "TORCH_HOME" in readme
    assert "browser session" in agent_guidance
    assert "LPS" in monai_skill
    compile(app_source, str(destination / "app.py"), "exec")
    compile(algorithm_source, str(destination / "algorithm.py"), "exec")

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import app; assert 'monai' not in sys.modules",
        ],
        cwd=destination,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_monai_template_converts_axes_and_preserves_geometry(tmp_path):
    destination = tmp_path / "monai-conversion"
    scaffold_project(destination, template="monai")
    module_path = destination / "algorithm.py"
    spec = importlib.util.spec_from_file_location(
        "generated_monai_algorithm",
        module_path,
    )
    assert spec is not None and spec.loader is not None
    algorithm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(algorithm)

    source = np.arange(24, dtype=np.float32).reshape(2, 3, 4, 1)
    image = imfusion.SharedImage(source)
    image.spacing = (0.7, 0.8, 1.2)
    image.image_to_world_matrix = np.array(
        [
            [1.0, 0.0, 0.0, 10.0],
            [0.0, 0.0, -1.0, 20.0],
            [0.0, 1.0, 0.0, 30.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )

    monai_voxels, ras_affine = algorithm.image_to_monai(image)

    assert monai_voxels.shape == (1, 4, 3, 2)
    np.testing.assert_array_equal(monai_voxels, source.transpose(3, 2, 1, 0))
    np.testing.assert_allclose(
        ras_affine,
        algorithm.LPS_TO_RAS @ np.asarray(image.pixel_to_world_matrix),
    )

    mask = algorithm.monai_to_imfusion(monai_voxels)
    output = algorithm.create_label_image(mask, image)
    np.testing.assert_array_equal(np.asarray(output), source.astype(np.uint8))
    np.testing.assert_allclose(
        output.image_to_world_matrix,
        image.image_to_world_matrix,
    )
    assert output.spacing == image.spacing


_CHAT_FACTORY_CHECK = """
import types

import app


def controller():
    return types.SimpleNamespace(
        data_model=types.SimpleNamespace(get_name=lambda data: ""),
        selected_data=[],
        _session=types.SimpleNamespace(send_message=lambda *args: None),
    )


first = app.build_workflow(controller())
second = app.build_workflow(controller())
assert [step.id for step in first.steps] == ["welcome", "conversation"]
assert first.get_step("conversation") is not second.get_step("conversation")
"""


def test_chat_scaffold_contains_a_provider_neutral_assistant(tmp_path):
    destination = tmp_path / "imaging-assistant"

    written = scaffold_project(
        destination,
        template="chat",
        title="Imaging Assistant",
    )

    assert "chat" in AVAILABLE_TEMPLATES
    assert _relative_paths(written, destination) == {
        ".claude/skills/work-with-imfusion-images/SKILL.md",
        ".cursor/skills/work-with-imfusion-images/SKILL.md",
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "app.py",
        "conversation.py",
        "pyproject.toml",
    }
    app_source = (destination / "app.py").read_text(encoding="utf-8")
    conversation_source = (destination / "conversation.py").read_text(encoding="utf-8")
    pyproject = (destination / "pyproject.toml").read_text(encoding="utf-8")
    readme = (destination / "README.md").read_text(encoding="utf-8")

    assert 'title="Imaging Assistant"' in app_source
    assert "ThemePreset.DARK" in app_source
    assert "def build_workflow(app)" in app_source
    assert "webapp.set_workflow(build_workflow)" in app_source
    assert "class ConversationStep(CustomStep)" in conversation_source
    assert "def reset_workflow_state" in conversation_source
    assert 'submit_action="send"' in conversation_source
    assert 'placeholder="Type your message here"' in conversation_source
    assert "{{" not in conversation_source
    assert 'name = "imaging-assistant"' in pyproject
    assert "openai" not in pyproject
    assert "timeout" in readme
    assert "No streaming." in readme
    compile(app_source, str(destination / "app.py"), "exec")
    compile(conversation_source, str(destination / "conversation.py"), "exec")

    completed = subprocess.run(
        [sys.executable, "-c", _CHAT_FACTORY_CHECK],
        cwd=destination,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


class _FakeImageSet(list):
    """Stand-in for a dataset that reports a name, modality, and geometry."""

    def __init__(self, images, name, modality=None):
        super().__init__(images)
        self.name = name
        self.modality = modality


def _chat_module(tmp_path, name):
    destination = tmp_path / name
    scaffold_project(destination, template="chat")
    spec = importlib.util.spec_from_file_location(
        f"generated_conversation_{name.replace('-', '_')}",
        destination / "conversation.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _chat_controller(selection=()):
    session = SimpleNamespace(send_message=lambda *_args: None)
    data_model = SimpleNamespace(get_name=lambda data: getattr(data, "name", ""))
    return SimpleNamespace(
        data_model=data_model,
        selected_data=list(selection),
        _session=session,
    )


def _texts(step):
    return [
        element["content"]
        for element in step.get_ui_config()["body"]
        if element["kind"] == "text"
    ]


def test_chat_template_records_turns_and_clears_the_prompt(tmp_path):
    module = _chat_module(tmp_path, "chat-turns")
    prompts = []

    def handler(prompt, *, context):
        prompts.append((prompt, context))
        return "The selection is a chest CT."

    dataset = _FakeImageSet(
        [SimpleNamespace(width=4, height=5, slices=6, spacing=(1.0, 1.0, 2.0))],
        "Chest CT",
        modality=SimpleNamespace(name="CT"),
    )
    step = module.ConversationStep(handler=handler)
    workflow = Workflow(_chat_controller([dataset]), [step])
    workflow.start()

    workflow.receive_step_data({"values": {"prompt": " What is this? "}})
    assert workflow.run_current_step("send") == (True, "")

    assert prompts == [
        (
            "What is this?",
            "Chest CT (modality CT, 4x5x6 voxels, spacing 1.00 x 1.00 x 2.00 mm)",
        )
    ]
    assert _texts(step) == [
        "> What is this?",
        "The selection is a chest CT.",
    ]
    assert step.values["prompt"] == ""


def test_chat_template_describes_an_empty_selection(tmp_path):
    module = _chat_module(tmp_path, "chat-context")
    contexts = []
    step = module.ConversationStep(
        handler=lambda prompt, *, context: contexts.append(context) or "Reply"
    )
    workflow = Workflow(_chat_controller(), [step])
    workflow.start()

    workflow.receive_step_data({"values": {"prompt": "Hello"}})
    workflow.run_current_step("send")

    assert contexts == ["No dataset is selected."]


def test_chat_template_reports_empty_and_failed_replies(tmp_path):
    module = _chat_module(tmp_path, "chat-notices")

    def failing_handler(prompt, *, context):
        raise RuntimeError("model unavailable")

    step = module.ConversationStep(handler=failing_handler)
    workflow = Workflow(_chat_controller(), [step])
    workflow.start()

    workflow.run_current_step("send")

    alerts = [
        element
        for element in step.get_ui_config()["body"]
        if element["kind"] == "alert"
    ]
    assert alerts == [
        {
            "kind": "alert",
            "content": "Type a message before sending.",
            "level": "warning",
        }
    ]

    workflow.receive_step_data({"values": {"prompt": "Hello"}})
    workflow.run_current_step("send")

    assert _texts(step) == ["> Hello"]
    assert "model unavailable" in step.get_ui_config()["body"][1]["content"]


def test_chat_template_caps_the_rendered_transcript(tmp_path):
    module = _chat_module(tmp_path, "chat-cap")
    step = module.ConversationStep(
        handler=lambda prompt, *, context: f"Reply to {prompt}",
        visible_turns=2,
    )
    workflow = Workflow(_chat_controller(), [step])
    workflow.start()

    for index in range(3):
        workflow.receive_step_data({"values": {"prompt": f"Question {index}"}})
        workflow.run_current_step("send")

    assert _texts(step) == [
        "> Question 2",
        "Reply to Question 2",
    ]


def test_chat_template_new_conversation_clears_the_transcript(tmp_path):
    module = _chat_module(tmp_path, "chat-new-conversation")
    step = module.ConversationStep(handler=lambda prompt, *, context: "Reply")
    workflow = Workflow(_chat_controller(), [step])
    workflow.start()

    workflow.receive_step_data({"values": {"prompt": "Hello"}})
    workflow.run_current_step("send")
    assert _texts(step) == ["> Hello", "Reply"]

    workflow.receive_step_data({"action": "new_conversation"})

    assert _texts(step) == [
        "Load an image, select it in the sidebar, then ask a question about it."
    ]
    assert step.can_proceed() == (True, "")


def test_chat_template_transcripts_are_isolated_between_sessions(tmp_path):
    module = _chat_module(tmp_path, "chat-isolation")
    template_step = module.ConversationStep(
        handler=lambda prompt, *, context: "Reply",
    )
    first = template_step.clone()
    second = template_step.clone()
    first_workflow = Workflow(_chat_controller(), [first])
    Workflow(_chat_controller(), [second])
    first_workflow.start()

    first_workflow.receive_step_data({"values": {"prompt": "Only mine"}})
    first_workflow.run_current_step("send")

    assert "> Only mine" in _texts(first)
    assert _texts(second) == [
        "Load an image, select it in the sidebar, then ask a question about it."
    ]


def test_scaffold_rejects_unknown_template(tmp_path):
    with pytest.raises(ValueError, match="Unknown template"):
        scaffold_project(tmp_path / "demo", template="unknown")


def test_init_parser_accepts_theme():
    args = build_parser().parse_args(["init", "my-demo", "--theme", "light"])
    assert args.command == "init"
    assert args.theme == "light"
    assert args.title is None


def test_init_parser_defaults_theme_to_dark():
    args = build_parser().parse_args(["init", "my-demo"])
    assert args.theme == "dark"


def test_scaffold_writes_selected_theme(tmp_path):
    destination = tmp_path / "themed-demo"

    scaffold_project(destination, theme="light")

    app_source = (destination / "app.py").read_text(encoding="utf-8")
    assert "ThemePreset.LIGHT" in app_source
    assert "ThemePreset.DARK" not in app_source
    compile(app_source, str(destination / "app.py"), "exec")


def test_scaffold_rejects_unknown_theme(tmp_path):
    with pytest.raises(ValueError, match="Unknown theme preset"):
        scaffold_project(tmp_path / "demo", theme="sepia")


def test_demo_forwards_host_and_port(monkeypatch):
    observed = {}

    def fake_main(host, port):
        observed.update(host=host, port=port)

    monkeypatch.setattr(
        "imfusion_webappkit.examples.webapp_demo.main",
        fake_main,
    )

    assert run_demo("0.0.0.0", 8123, open_browser=False) == 0
    assert observed == {"host": "0.0.0.0", "port": 8123}


def test_demo_workflow_forwards_host_and_port(monkeypatch):
    observed = {}

    def fake_main(host, port):
        observed.update(host=host, port=port)

    monkeypatch.setattr(
        "imfusion_webappkit.examples.workflow_demo.main",
        fake_main,
    )

    assert run_demo("0.0.0.0", 8123, open_browser=False, workflow=True) == 0
    assert observed == {"host": "0.0.0.0", "port": 8123}


def test_demo_parser_accepts_workflow_flag():
    args = build_parser().parse_args(["demo", "--workflow", "--no-open"])
    assert args.command == "demo"
    assert args.workflow is True
    assert args.no_open is True


def test_record_parser_reads_a_demo_reference_and_an_output():
    args = build_parser().parse_args(
        ["record", "demos/threshold.py:spec", "-o", "dist/demo", "--skip-client-build"]
    )
    assert args.command == "record"
    assert args.demo == "demos/threshold.py:spec"
    assert args.output == Path("dist/demo")
    assert args.skip_client_build is True


def test_record_requires_an_output_directory(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["record", "demos/threshold.py"])
    assert "--output" in capsys.readouterr().err


def test_record_reports_an_unloadable_demo_without_a_traceback(capsys, tmp_path):
    assert run_record("no_such_module:spec", tmp_path / "out") == 1
    assert "Could not load no_such_module:spec" in capsys.readouterr().out


def test_record_asks_which_spec_when_a_file_holds_several(tmp_path, capsys):
    module = tmp_path / "two_demos.py"
    module.write_text(
        "from imfusion_webappkit.static_demo import StaticDemoSpec\n"
        "first = StaticDemoSpec(app=lambda: None)\n"
        "second = StaticDemoSpec(app=lambda: None)\n",
        encoding="utf-8",
    )

    assert run_record(str(module), tmp_path / "out") == 1
    assert "defines 2 demo specs" in capsys.readouterr().out


def test_record_loads_a_named_spec_from_a_file(tmp_path):
    module = tmp_path / "one_demo.py"
    module.write_text(
        "from imfusion_webappkit.static_demo import StaticDemoSpec\n"
        "spec = StaticDemoSpec(app=lambda: None)\n",
        encoding="utf-8",
    )

    assert isinstance(load_spec(f"{module}:spec"), StaticDemoSpec)
    assert isinstance(load_spec(str(module)), StaticDemoSpec)
