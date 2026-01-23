from src.verify_backpack import _matches_target
from tests.test_template import TestTemplate


class TestVerifyBackpack(TestTemplate):
    def test_matches_target_by_address(self):
        assert _matches_target(
            device_name="YS6249181011L",
            device_address="ABCDEF12-3456-7890-ABCD-EF1234567890",
            target_name=None,
            target_address="abcdef12-3456-7890-abcd-ef1234567890",
        )

    def test_matches_target_by_name_substring(self):
        assert _matches_target(
            device_name="YS6249181011L",
            device_address="ABCDEF12-3456-7890-ABCD-EF1234567890",
            target_name="ys6249",
            target_address=None,
        )

    def test_matches_target_false_when_no_match(self):
        assert not _matches_target(
            device_name="YS6249181011L",
            device_address="ABCDEF12-3456-7890-ABCD-EF1234567890",
            target_name="other",
            target_address="11111111-2222-3333-4444-555555555555",
        )
