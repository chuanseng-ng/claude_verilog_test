# I2C functional-coverage model (bead h367 pilot)

DUT: `rtl/periph/i2c_controller.sv` (+ `i2c_bit_engine.sv`), I2C master, APB4 slave, 12 registers.
Implementation: `tb/cocotb/soc/i2c_cov.py`. Mechanism, flow and rollout:
`FUNCTIONAL_COVERAGE.md`. The bins come from the controller header (the spec of record for this
IP) and the I2C protocol, not from what the tests happen to do. Names are `i2c.<group>.<coverpoint>`.

Sources of samples: **bus** = the `I2CSlave` BFM event stream; **apb** = `APB4Master` transfers and
the tests' `_peek`; **scenario** = a call placed after the test's own assertions. No RTL is touched
and no DUT signal is read by the model.

Result of the first complete run: **138 bins, all hit, no waivers** (table at the end).

## bus: what the master did on the wire (source: bus)

| Coverpoint | Bins | Why |
| :--------- | :--- | :-- |
| `start_kind` | `start`, `rstart_after_write`, `rstart_after_read` | START and the two repeated-START contexts. A START that follows an aborted transfer is not counted as a repeated START. |
| `addr_dir`, `addr_ack`, cross `addr_result` | write/read x ack/nack (4 cross bins) | Address phase outcome per direction. |
| `wr_data_ack` | ack, nack | A slave NACK on write data. |
| `rd_master_ack` | ack, nack | The master ACKs every read byte except a NACK_LAST final one. |
| `wr_bytes` | 0 (address only), 1, 2, 3-4, 5-8, 9-16, 17+ | Per write segment with an ACKed address; 8 is the FIFO depth, 9-16 and 17+ need FIFO refill during the transfer. Counts every data byte on the wire. |
| `rd_bytes` | 1, 2, 3-4, 5-8, 9-16, 17+ | Same for reads (RX FIFO full / drain). |
| `segments_per_txn` | 1, 2, 3+ | START..STOP: plain, one repeated START, a chain. |
| `stop_after` | write, read, addr_nack | What the STOP closed. |
| `stretch_at` | addr_bit, addr_ack, wr_bit, wr_ack, rd_bit, rd_ack | Mandatory clock stretching, where the slave held SCL. `STRETCH` is reported by the BFM (not in `events`). |
| `stretch_mode` | single_fall, every_fall | One stretch vs a slave that stretches every bit. |

## cmd: the I2C_CMD words issued (source: apb)

| Coverpoint | Bins | Why |
| :--------- | :--- | :-- |
| `shape` | `S`tart x (none, `W`rite, `R`ead, both) x `P`stop = 16 | Every START/op/STOP combination, including address-only (`S--P`, `S---`) and both-flag (write wins). Shapes the engine ignores are still bins: issuing them is the stimulus; ignoring them is checked by `err.cmd_ignored`. |
| `count` | 0 (means 1), 1, 2-8, 9-254, 255 | COUNT field edges, including beyond the 8-byte FIFOs and the field maximum. |
| `read_last` | acked, nacked | READ with NACK_LAST = 0 / 1. |
| `loopback_op` | write, read | A command run while CTRL.LOOPBACK is set. |

## cfg: configuration programmed (source: apb)

| Coverpoint | Bins | Why |
| :--------- | :--- | :-- |
| `clkdiv` | 0-2 (clamped), 3 (minimum), 4-61, 62 (400 kHz at 100 MHz), 63-248, 249 (100 kHz), 250-0xFFFE, 0xFFFF | Divider settings: the hardware clamp, the minimum, both standard rates, mid range and the wide tick counter. |
| `rx_thr` | 0, 1, 2-8, 9-15 | RX threshold; 0 behaves as 1, 9-15 never fire. |
| `ctrl_mode` | enable, loopback, disable | CTRL write that enables, enables loopback, or disables (aborts). |
| `timeout` | 0 (off), 1-1023, 1024-0xFFFE, 0xFFFF (reset) | Watchdog settings; 0 disables. |
| `irq_en` | done, nack, arb_lost, timeout, rx_threshold | Each interrupt source enabled. |

## irq / status / fifo: what software observed (source: apb)

| Coverpoint | Bins | Why |
| :--------- | :--- | :-- |
| `irq.cause_seen` | done, nack, arb_lost, timeout, rx_threshold | Every interrupt cause seen pending in IRQ_STAT. |
| `irq.w1c` | done, nack, arb_lost, timeout | Each sticky cause cleared with W1C (rx_threshold is a live level). |
| `irq.gating` | asserted, masked | A pending cause that does / does not reach `irq_o` given IRQ_EN. |
| `status.seen` | busy, txn_active, nack, arb_lost, timeout | STATUS flags seen set. |
| `fifo.tx_state`, `fifo.rx_state` | empty, partial, full | FIFO_STAT views. |

## err: error and recovery paths

| Coverpoint | Bins | Source | Why |
| :--------- | :--- | :----- | :-- |
| `nack_where` | address, write_data | bus | Where the slave NACKed. |
| `nack_state` | bus_held, stop_sent | apb | After a NACK the master either holds the bus (no STOP requested) or released it. |
| `arb_loss` | address_bit, data_bit, read_nack_slot, rstart_setup | scenario | Where arbitration was lost; sampled after `arb_lost`-only and released-lines assertions. |
| `timeout_cause` | scl_stretched, bus_busy_wait, tx_starve, rx_full | scenario | Which bounded wait expired; sampled after the sticky `timeout` assertion. |
| `cmd_ignored` | disabled, illegal_shape, no_strobe, busy | scenario | A CMD write silently dropped; sampled after the bus proved quiet. |
| `abort` | en_cleared, reset | scenario | A transfer aborted by CTRL.EN = 0 or by reset, after the post-abort state checks. |

## soc: reached through the real fabric (`test_soc_i2c.py`, source: scenario)

`path`: `reset_values`, `loopback_write`, `loopback_read`, `irq_to_cpu` (test_soc_i2c) and
`real_pad_write`, `real_pad_read`, `real_pad_addr_nack` (test_soc_i2c_real_pads), each sampled after
that test's firmware-score and bus-event assertions. The real-pad test also feeds the `bus` group
through the BFM observer.

## Reachability and waivers

No waivers. Every bin was reachable; the ones the original suites missed got tests:

| Bin(s) found unreached by the first run | Test added |
| :-- | :-- |
| `wr_bytes.n17_up`, `rd_bytes.n17_up` | `test_i2c_transfers_longer_than_both_fifos` |
| `segments_per_txn.three_up`, `start_kind.rstart_after_read` | `test_i2c_repeated_start_chain_write_read_write` |
| `cmd.shape` `S---`, `S--P`, `SWR-`, `-WR-`, `-WRP` | `test_i2c_command_shapes_address_only_and_both_flags` |
| `cmd.count.max_255` | `test_i2c_cmd_count_255_abandoned_on_data_nack` |
| `err.timeout_cause.rx_full` | `test_i2c_rx_full_wait_times_out` |

## Known limits of the model

* It checks that scenarios occurred, not that the DUT's data was right: that stays the tests' job.
* `arb_loss`, `timeout_cause`, `cmd_ignored`, `abort` and `soc.path` are declarations made after
  the test's assertions, not independent observations.
* Not modelled: back-to-back START timing (tBUF/tHD;STA, measured by dedicated tests), 10-bit
  addressing (not implemented), multi-master beyond arbitration loss, SDA setup/hold.
