from comfy.comfy_types import IO


class XimiStringInput:
    """Widget-based string input node.

    Lets you type/paste a string (URL/path/text) and outputs it
    for use by other nodes.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": (
                    IO.STRING,
                    {
                        "default": "",
                        "multiline": False,
                        "tooltip": "Enter a string (URL/path/text) to output",
                    },
                )
            }
        }

    RETURN_TYPES = (IO.STRING,)
    RETURN_NAMES = ("string",)
    FUNCTION = "produce"
    CATEGORY = "ximi-ai/utils"

    def produce(self, value: str):
        return (value,)


NODE_CLASS_MAPPINGS = {
    "XimiStringInput": XimiStringInput,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XimiStringInput": "String Input (ximi-ai)",
}

