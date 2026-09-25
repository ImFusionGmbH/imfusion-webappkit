from imfusion_webappkit.workflow import ExportStep


def test_export_can_be_required_before_finish():
    step = ExportStep()

    assert step.can_proceed() == (False, "Please export your results")
    assert step.get_ui_config()["formats"] == ["imf", "nii.gz", "dicom"]

    step.receive_data({"exported": True})

    assert step.can_proceed() == (True, "")
    assert step.get_ui_config()["exported"] is True


def test_finish_can_be_enabled_before_export():
    step = ExportStep(require_export_before_finish=False)

    assert step.can_proceed() == (True, "")


def test_export_formats_are_normalized_and_deduplicated():
    step = ExportStep(formats=["NIfTI", ".dcm", "dicom"])

    assert step.get_ui_config()["formats"] == ["nii.gz", "dicom"]
