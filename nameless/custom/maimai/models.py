from dataclasses import dataclass


@dataclass(kw_only=True)
class MaimaiUser:
    friend_code: int
    name: str
    rating: int
    avatar_img: str
