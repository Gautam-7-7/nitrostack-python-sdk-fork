import sys
import os
import threading
import time
import pytest

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack.core.di import DIContainer, injectable
from nitrostack.core.errors import DependencyResolutionError, CircularDependencyError

# Reset the DIContainer before each test
@pytest.fixture(autouse=True)
def reset_container():
    DIContainer.reset()
    yield
    DIContainer.reset()

def test_basic_auto_resolution():
    @injectable()
    class DependencyA:
        def __init__(self):
            self.value = "A"

    @injectable()
    class DependencyB:
        def __init__(self, dep_a: DependencyA):
            self.dep_a = dep_a
            self.value = "B"

    container = DIContainer.get_instance()
    b = container.resolve(DependencyB)
    
    assert b.value == "B"
    assert b.dep_a.value == "A"
    # Ensure they are singletons
    assert container.resolve(DependencyA) is b.dep_a

def test_auto_resolution_with_defaults():
    @injectable()
    class DependencyWithDefault:
        def __init__(self, name: str = "default_name"):
            self.name = name

    container = DIContainer.get_instance()
    instance = container.resolve(DependencyWithDefault)
    assert instance.name == "default_name"

def test_custom_token_mapping():
    @injectable(provide="DatabaseConnection")
    class PostgresConnection:
        def __init__(self):
            self.conn_str = "postgresql://localhost"

    @injectable()
    class QueryRunner:
        def __init__(self, db: "DatabaseConnection"):
            self.db = db

    container = DIContainer.get_instance()
    
    # Check resolving via string token
    db_instance = container.resolve("DatabaseConnection")
    assert db_instance.conn_str == "postgresql://localhost"

    # Check resolving via the class itself (it should map to the same singleton instance)
    db_class_instance = container.resolve(PostgresConnection)
    assert db_class_instance is db_instance

    # Check injection into QueryRunner
    runner = container.resolve(QueryRunner)
    assert runner.db is db_instance

def test_circular_dependency_detection():
    # Setup circular dependency: ServiceA -> ServiceB -> ServiceA
    @injectable()
    class ServiceB:
        pass

    @injectable()
    class ServiceA:
        def __init__(self, b: ServiceB):
            self.b = b

    # Manually configure ServiceB to depend on ServiceA to create the cycle
    ServiceB._mcp_deps = [ServiceA]

    container = DIContainer.get_instance()
    
    with pytest.raises(CircularDependencyError) as exc_info:
        container.resolve(ServiceA)
        
    assert "Circular dependency detected" in str(exc_info.value)
    # The path should display the circular loop
    assert "ServiceA" in str(exc_info.value)
    assert "ServiceB" in str(exc_info.value)

def test_thread_safety():
    @injectable()
    class SlowSingleton:
        def __init__(self):
            # Introduce a slight delay to trigger concurrency issues if not locked
            time.sleep(0.05)
            self.id = threading.get_ident()

    container = DIContainer.get_instance()
    instances = []
    errors = []

    def worker():
        try:
            instance = container.resolve(SlowSingleton)
            instances.append(instance)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors occurred during concurrent resolution: {errors}"
    assert len(instances) == 10
    # All threads must have resolved the exact same instance reference
    first_instance = instances[0]
    for inst in instances[1:]:
        assert inst is first_instance
