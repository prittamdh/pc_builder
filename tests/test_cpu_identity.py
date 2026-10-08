"""CPU identity keys (2026-10-02 review of live data).

The key was brand + series + model number from the LLM. The model number already
names the CPU, so the series only added ways to split one: a 9700X labelled "Ryzen 9",
a Core Ultra 5 225 and a 5700X whose brand came back "Unknown", and TPS's "9950X 3D"
read as a 9950X in a "Ryzen 9 3D" series.
"""
import pytest

from matching.cpu_identity import cpu_key


@pytest.mark.parametrize("a, b", [
    # (brand, series, model_number, title) pairs that are the same CPU
    (("AMD", "Ryzen 7", "9700X", "AMD Ryzen 7 9700X"),
     ("AMD", "Ryzen 9", "9700X", "AMD Ryzen 7 9700X 8-Core 16-Threads 9000 Series Desktop Processor")),
    (("Intel", "Core Ultra 5", "225", "Intel Core Ultra 5 225"),
     ("Unknown", "", "225", "Intel Core Ultra 5 225 Processor")),
    (("AMD", "Ryzen 7", "5700X", "AMD Ryzen 7 5700X OEM Tray Processor"),
     ("Unknown", "", "5700X", "AMD Ryzen 7 5700X OEM with NO Stock Cooler Desktop Processor")),
    (("AMD", "Ryzen 9", "9950X3D", "AMD Ryzen 9 9950X3D Processor"),
     ("AMD", "Ryzen 9 3D", "9950X", "AMD Ryzen 9 9950X 3D 16 Cores 32 Threads 5.7GHz 128MB Cache AM5")),
    (("AMD", "Ryzen 7", "7800X3D", "AMD Ryzen 7 7800X3D"),
     ("AMD", "Ryzen 7", "7800X 3D", "AMD Ryzen 7 7800X 3D 8 Cores 16 Threads")),
    (("Intel", "Core i5", "14400F", "Intel Core i5-14400F"),
     ("Intel", "Core i5", "i5-14400F", "Intel Core I5-14400F Processor BX8071514400F")),
])
def test_same_cpu_same_key(a, b):
    assert cpu_key(*a) == cpu_key(*b)


@pytest.mark.parametrize("a, b", [
    (("AMD", "Ryzen 5", "7600", "AMD Ryzen 5 7600"), ("AMD", "Ryzen 5", "7600X", "AMD Ryzen 5 7600X")),
    (("AMD", "Ryzen 9", "9950X", "AMD Ryzen 9 9950X"), ("AMD", "Ryzen 9", "9950X3D", "AMD Ryzen 9 9950X3D")),
    (("Intel", "Core i5", "14400", "Intel Core i5 14400"), ("Intel", "Core i5", "14400F", "Intel Core i5 14400F")),
    (("AMD", "Ryzen 7", "8700G", "AMD Ryzen 7 8700G"), ("AMD", "Ryzen 7 PRO", "8700G", "AMD Ryzen 7 PRO 8700G")),
])
def test_different_cpus_stay_apart(a, b):
    assert cpu_key(*a) != cpu_key(*b)


def test_key_shape():
    assert cpu_key("AMD", "Ryzen 7", "7800X3D", "AMD Ryzen 7 7800X3D") == "cpu:amd:7800x3d"
    assert cpu_key("AMD", "Threadripper PRO", "7995WX", "AMD Ryzen Threadripper Pro 7995WX") == "cpu:amd:7995wx"
