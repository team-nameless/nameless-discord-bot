import nameless.utils as utils


class TestUtility:
    def test_url_check_true(self):
        assert utils.is_an_url("http://example.com")
        assert utils.is_an_url("https://discord.com")
        assert utils.is_an_url("osump://696969")
        assert utils.is_an_url("//example.com")

    def test_url_check_false(self):
        assert not utils.is_an_url("bao.moe")
        assert not utils.is_an_url("discord.com")
        assert not utils.is_an_url("m.me")
