from comfy.comfy_types import IO


class XimiStringPass:
    """Pass-through node for strings (urls/paths/text)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "string": (
                    IO.STRING,
                    {
                        "default": "",
                        "multiline": False,
                        "forceInput": True,
                        "tooltip": "Connect a string from another node (URL/path/text)",
                    },
                )
            }
        }

    RETURN_TYPES = (IO.STRING,)
    RETURN_NAMES = ("string",)
    FUNCTION = "pass_through"
    CATEGORY = "ximi-ai/utils"

    def pass_through(self, string: str):
        return (string,)


NODE_CLASS_MAPPINGS = {
    "XimiStringPass": XimiStringPass,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XimiStringPass": "String Pass (ximi-ai)",
}

