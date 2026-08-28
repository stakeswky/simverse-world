from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts" / "run-challenge-e2e.sh").read_text(encoding="utf-8")
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


class ChallengeE2EIsolationContractTests(unittest.TestCase):
    def test_compose_host_ports_are_parameterized(self) -> None:
        self.assertIn("${SIMVERSE_POSTGRES_HOST_PORT:-5432}:5432", COMPOSE)
        self.assertIn("${SIMVERSE_REDIS_HOST_PORT:-6379}:6379", COMPOSE)

    def test_isolated_mode_requires_a_scoped_project_name(self) -> None:
        self.assertIn("SIMVERSE_E2E_ISOLATED", SCRIPT)
        self.assertIn("SIMVERSE_E2E_PROJECT_NAME", SCRIPT)
        self.assertIn("docker compose -p", SCRIPT)

    def test_isolated_mode_uses_configured_host_ports(self) -> None:
        self.assertIn("SIMVERSE_POSTGRES_HOST_PORT", SCRIPT)
        self.assertIn("SIMVERSE_REDIS_HOST_PORT", SCRIPT)
        self.assertIn("localhost:${simverse_postgres_port}", SCRIPT)
        self.assertIn("localhost:${simverse_redis_port}", SCRIPT)

    def test_isolated_cleanup_removes_only_owned_project_and_volumes(self) -> None:
        self.assertIn("down -v --remove-orphans", SCRIPT)
        self.assertIn("simverse_infra_owned", SCRIPT)
        self.assertIn("simverse_infra_drain", SCRIPT)


if __name__ == "__main__":
    unittest.main()
