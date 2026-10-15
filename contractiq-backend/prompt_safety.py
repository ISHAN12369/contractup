"""Serialize evidence as data inside delimiters that document text cannot close."""
import json


def untrusted(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e")
    return "<untrusted_contract_data>\n" + payload + "\n</untrusted_contract_data>"
