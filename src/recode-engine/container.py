class ContainerHelper:
    @staticmethod
    def preferred_container(codec: str) -> str:
        """Returns codec's preferred container's associated file extension (no preceding dot)"""
        return "mkv"
