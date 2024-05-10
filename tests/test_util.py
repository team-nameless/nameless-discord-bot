from nameless.commons import Utility


class TestUtility:
    def test_url_check_true(self):
        assert Utility.is_an_url("http://example.com")
        assert Utility.is_an_url("https://discord.com")
        assert Utility.is_an_url("osump://696969")
        assert Utility.is_an_url("//example.com")

    def test_url_check_false(self):
        assert not Utility.is_an_url("bao.moe")
        assert not Utility.is_an_url("discord.com")
        assert not Utility.is_an_url("m.me")
