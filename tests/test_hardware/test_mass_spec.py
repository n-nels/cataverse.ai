from __future__ import annotations

from unittest.mock import MagicMock

from src.hardware.mass_spec import ExtrelMassSpec


def test_read_registers_success_returns_register_list() -> None:
    client = MagicMock()
    rr = MagicMock()
    rr.isError.return_value = False
    rr.registers = [1, 2, 3]
    client.read_holding_registers.return_value = rr

    ms = ExtrelMassSpec(client)
    regs = ms.read_registers(address=2, count=3, unit=1)

    assert regs == [1, 2, 3]
    client.read_holding_registers.assert_called_once_with(
        address=2,
        count=3,
        device_id=1,
    )


def test_write_register_returns_true_on_success() -> None:
    client = MagicMock()
    wr = MagicMock()
    wr.isError.return_value = False
    client.write_register.return_value = wr

    ms = ExtrelMassSpec(client)

    assert ms.write_register(address=1, value=2) is True
    client.write_register.assert_called_once_with(address=1, value=2)


def test_decode_ieee754_cdab_zero_value() -> None:
    assert ExtrelMassSpec.decode_ieee754_cdab(0, 0) == 0.0


def test_decode_ieee754_cdab_known_nonzero_value() -> None:
    # 1.5 in big-endian bytes is 0x3f c0 00 00; CDAB pair is r1=0x3fc0, r0=0x0000
    value = ExtrelMassSpec.decode_ieee754_cdab(r0=0x0000, r1=0x3FC0)
    assert value == 1.5
