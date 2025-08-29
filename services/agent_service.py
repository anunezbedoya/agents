from utils.adk_client import ADKClient

class AgentService:
    def __init__(self):
        self.adk_client = ADKClient()

    def diagnose_ticket(self, ticket_text: str):
        return self.adk_client.diagnose_ticket(ticket_text)