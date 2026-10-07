import pytest

from navfm.collection.source_stability import verify_source_stability


def test_new_import_does_not_mean_existing_source_changed():
    expected = {"policy.py": "original"}
    assert verify_source_stability(expected, {**expected, "crop.py": "new"}) == {
        "policy.py": "original",
        "crop.py": "new",
    }
    assert expected == {"policy.py": "original"}


@pytest.mark.parametrize("observed", [{"policy.py": "modified"}, {}])
def test_existing_modification_or_disappearance_fails_closed(observed):
    with pytest.raises(ValueError, match="changed or disappeared"):
        verify_source_stability({"policy.py": "original"}, observed)
