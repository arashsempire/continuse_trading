import asyncio
from utils import BaseLogger


class Strategy(BaseLogger):
    def __init__(self):
        # Configure logging to write to a file named `LBSTG01.log`
        super().__init__()
        self.log = self.log.bind()

    async def enter_long(self):
        """Simulate entering a long trade."""
        self.log.debug("Entering long trade")
        # print("Entering long trade")

    async def exit_long(self):
        """Simulate exiting a long trade."""
        self.log.debug("Exiting long trade")
        # print("Exiting long trade")

    async def enter_short(self):
        """Simulate entering a short trade."""
        self.log.debug("Entering short trade")
        # print("Entering short trade")

    async def exit_short(self):
        """Simulate exiting a short trade."""
        self.log.debug("Exiting short trade")
        # print("Exiting short trade")

    async def long_trades(self):
        """Execute a long trade: enter long, wait 5 seconds, then exit long."""
        await self.enter_long()
        # await asyncio.sleep(5)  # Wait for 5 seconds
        await self.exit_long()
        self.log.info("executed long trade")

    async def short_trades(self):
        """Execute a short trade: enter short, wait 5 seconds, then exit short."""
        await self.enter_short()
        # await asyncio.sleep(5)  # Wait for 5 seconds
        await self.exit_short()
        self.log.info("executed short trade")


# Example usage
async def main():
    strategy = Strategy()

    # Execute long trades
    await strategy.long_trades()

    # Execute short trades
    await strategy.short_trades()

# Run the main function
if __name__ == "__main__":
    asyncio.run(main())
