from camoufox import AsyncCamoufox
import asyncio

async def main():
    async with AsyncCamoufox(headless=True, geoip=True, humanize=True, i_know_what_im_doing=True, config={'forceScopeAccess': True}, disable_coop=True) as browser:
        page = await browser.new_page()
        

asyncio.run(main())
