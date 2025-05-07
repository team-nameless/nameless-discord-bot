import os
from typing import Final

import requests
from bs4 import BeautifulSoup, Tag

from nameless.custom.maimai.models import MaimaiUser

__all__ = ["MaimaiClient"]


class MaimaiClient:
    """maimaiDX data crawler."""

    _HOME_URL: Final[str] = "https://maimaidx-eng.com/maimai-mobile"

    def __init__(self):
        self.session: requests.Session = requests.Session()
        self.own_friend_code: int = 0

        self._pre_populate_cookies()
        self._get_self_friend_code()

    def _pre_populate_cookies(self):
        """Send requests to populate cookies."""
        params = {
            "site_id": "maimaidxex",
            "redirect_url": "https://maimaidx-eng.com/maimai-mobile/",
            "back_url": "https://maimai.sega.com/",
        }

        self.session.get(
            "https://lng-tgk-aime-gw.am-all.net/common_auth/login", params=params
        )

        auth_data = {
            "sid": os.getenv("SEGA_ID_USER", ""),
            "password": os.getenv("SEGA_ID_PASS", ""),
            "retention": "1",
        }

        self.session.post(
            "https://lng-tgk-aime-gw.am-all.net/common_auth/login/sid", data=auth_data
        )

    def _create_html_parser(self, html: str) -> BeautifulSoup:
        """Create bs4 html parser from HTML."""
        return BeautifulSoup(html, "html.parser")

    def _get_self_friend_code(self):
        """Stoopid SEGA does not allow you to query your own code."""
        res = self.session.get(f"{self._HOME_URL}/friend/userFriendCode")
        soup = self._create_html_parser(res.text)
        code_tag = soup.find(
            "div", {"class": "see_through_block m_t_5 m_b_5 p_5 t_c f_15"}
        )

        assert code_tag is not None
        self.own_friend_code = int(code_tag.text)

    def find_by_friend_code(self, friend_code: int) -> MaimaiUser:
        """Get user by friend code.

        Parameters
        ----------
        friend_code: int
            The maimai friend code. Ask your friend for one.
        """
        if friend_code == self.own_friend_code:
            request_url = f"{self._HOME_URL}/friend/userFriendCode"
        else:
            request_url = (
                f"{self._HOME_URL}/friend/search/searchUser?friendCode={friend_code}"
            )

        res = self.session.get(request_url)
        soup = self._create_html_parser(res.text)

        name_tag = soup.find("div", {"class": "name_block f_l f_16"})
        rate_tag = soup.find("div", {"class": "rating_block"})
        img_tag = soup.find("img", {"class": "w_112 f_l"})

        assert name_tag is not None
        assert rate_tag is not None
        assert img_tag is not None

        assert isinstance(img_tag, Tag)

        return MaimaiUser(
            friend_code=friend_code,
            name=name_tag.text,
            rating=int(rate_tag.text),
            avatar_img=img_tag.attrs["src"],
        )
