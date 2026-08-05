"""Tests for GarminClientWrapper, including safe_call's JSON-safety normalization."""

from garmin_connect_mcp.client import GarminAPIError, _to_json_safe


class FakeHttpResponse:
    """Mimics garminconnect's internal EmptyJSONResp / requests.Response shape: not
    itself JSON-serializable, but exposes a .json() method that returns real data."""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class BrokenJsonResponse:
    """A response-like object whose .json() call itself raises."""

    def json(self):
        raise ValueError("not actually JSON")


class TestToJsonSafe:
    def test_passes_through_plain_types_unchanged(self):
        for value in [{"a": 1}, [1, 2, 3], "text", 42, 3.14, True, None]:
            assert _to_json_safe(value) == value

    def test_calls_json_method_on_response_like_objects(self):
        response = FakeHttpResponse({"result": "ok"})

        assert _to_json_safe(response) == {"result": "ok"}

    def test_falls_back_to_str_when_json_method_raises(self):
        result = _to_json_safe(BrokenJsonResponse())

        assert isinstance(result, str)

    def test_falls_back_to_str_for_objects_without_json_method(self):
        class Opaque:
            def __repr__(self):
                return "<Opaque>"

        assert _to_json_safe(Opaque()) == "<Opaque>"


class TestSafeCallNormalization:
    def test_safe_call_normalizes_a_response_like_return_value(self, wrapper, client_stub):
        client_stub._method_results["delete_activity"] = FakeHttpResponse({})

        result = wrapper.safe_call("delete_activity", 123)

        assert result == {}

    def test_safe_call_passes_through_plain_dict_unchanged(self, wrapper, client_stub):
        client_stub._method_results["get_workout_by_id"] = {"workoutId": 1, "workoutName": "X"}

        result = wrapper.safe_call("get_workout_by_id", 1)

        assert result == {"workoutId": 1, "workoutName": "X"}

    def test_safe_call_still_raises_garmin_api_error_for_unknown_method(self, wrapper):
        try:
            wrapper.safe_call("this_method_does_not_exist")
            raise AssertionError("expected GarminAPIError")
        except GarminAPIError as e:
            assert "not found" in e.message
