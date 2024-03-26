from enum import Enum


class Message(Enum):
    def __new__(cls, code: str, message: str, status_code: int):
        entry = object.__new__(cls)
        entry.code = entry._value_ = code
        entry.message = message
        entry.status_code = status_code
        return entry


class MessageEnum(Message):
    SUCCESS = ('0', 'Success', 200)
    BAD_REQUEST = ('10001', 'Bad Request', 400)
    UNAUTHORIZED = ('10002', 'Unauthorized', 401)
    INTERNAL_ERROR = ('10003', 'Internal Error', 500)
