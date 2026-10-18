/* uart_boot_proto.h -- wire protocol shared by the ROM bootloader (uart_boot.c),
 * the host tool (tools/fw/uart_load.py) and the tests.  tb/tests/test_uart_load.py
 * parses this file and fails if the Python constants drift from it.
 *
 * Host -> target frame (all multi-byte fields little-endian):
 *     SOF(0x7E) CMD LEN_LO LEN_HI PAYLOAD[LEN] CRC32[4]
 *   CRC32 = IEEE 802.3 / zlib.crc32 over CMD, LEN_LO, LEN_HI and PAYLOAD.
 * Target -> host response:
 *     ACK(0x06) N PAYLOAD[N]        or        NAK(0x15) ERR
 */
#ifndef UART_BOOT_PROTO_H
#define UART_BOOT_PROTO_H

#define BL_PROTO_VERSION   1

#define BL_SOF             0x7E
#define BL_ACK             0x06
#define BL_NAK             0x15

#define BL_CMD_INFO        0x01  /* len 0  -> ACK [ver, max_data(2), load_lo(4), load_hi(4)] */
#define BL_CMD_WRITE       0x02  /* addr(4) + data[1..max_data] -> ACK [] */
#define BL_CMD_CRC         0x03  /* addr(4) + nbytes(4) -> ACK [crc32(4)] */
#define BL_CMD_JUMP        0x04  /* entry(4) -> ACK [] then clean D$, FENCE.I, jump */

#define BL_ERR_CRC         0x01
#define BL_ERR_CMD         0x02
#define BL_ERR_LEN         0x03
#define BL_ERR_ADDR        0x04
#define BL_ERR_TIMEOUT     0x05

#define BL_BANNER          "\nUBL1\n"

#endif
