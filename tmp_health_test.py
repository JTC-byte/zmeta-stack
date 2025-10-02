import asyncio\nfrom backend.app.main import healthz\n\nasync def main():\n    result = await healthz()\n    print(result)\n\nasyncio.run(main())
