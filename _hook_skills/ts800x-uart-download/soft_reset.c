/******************************************************************************
 * @file:   soft_reset.c
 * @author: D_Lobster
 * @brief:  Transport-independent TS800X A0/A1 development protocol parser
 * @date:   2026-07-17
 ******************************************************************************/

#include "soft_reset.h"

#include <stddef.h>

#define SOFT_RESET_SOF              0x55U
#define SOFT_RESET_EOF              0xAAU
#define SOFT_RESET_VERSION          0x01U
#define SOFT_RESET_CMD_A0           0xA0U
#define SOFT_RESET_CMD_A1           0xA1U
#define SOFT_RESET_FLAG_ACK         0x01U
#define SOFT_RESET_PAYLOAD_SIZE     4U
#define SOFT_RESET_QUEUE_SIZE       64U
#define SOFT_RESET_QUEUE_MASK       (SOFT_RESET_QUEUE_SIZE - 1U)

static const uint8_t s_magic_key[SOFT_RESET_PAYLOAD_SIZE] = {'T', 'S', '8', '0'};
static volatile uint8_t s_rx_queue[SOFT_RESET_QUEUE_SIZE];
static volatile uint8_t s_rx_head;
static volatile uint8_t s_rx_tail;
static volatile uint8_t s_rx_overflow;
static uint8_t s_frame[SOFT_RESET_FRAME_SIZE];
static uint8_t s_frame_length;

/**
 * @brief:  Calculate protocol CRC-8 with polynomial 0x07.
 * @param:  data: Input byte array.
 * @param:  length: Number of input bytes.
 * @retval: Calculated CRC byte.
 */
static uint8_t calculate_crc8(const uint8_t *data, uint8_t length) {
    uint8_t crc = 0U;
    uint8_t index;
    uint8_t bit;

    for (index = 0U; index < length; index++) {
        crc ^= data[index];
        for (bit = 0U; bit < 8U; bit++) {
            crc = (crc & 0x80U) != 0U
                ? (uint8_t)((crc << 1U) ^ 0x07U)
                : (uint8_t)(crc << 1U);
        }
    }
    return crc;
}

/**
 * @brief:  Validate a complete fixed-size A0/A1 frame.
 * @param:  None.
 * @retval: 1 when all fixed fields, key, CRC, and EOF are valid.
 */
static uint8_t is_frame_valid(void) {
    uint8_t index;

    if (s_frame[0] != SOFT_RESET_SOF || s_frame[1] != SOFT_RESET_VERSION) {
        return 0U;
    }
    if (s_frame[6] != SOFT_RESET_PAYLOAD_SIZE || s_frame[7] != 0U) {
        return 0U;
    }
    for (index = 0U; index < SOFT_RESET_PAYLOAD_SIZE; index++) {
        if (s_frame[8U + index] != s_magic_key[index]) {
            return 0U;
        }
    }
    if (s_frame[12] != calculate_crc8(&s_frame[1], 11U)) {
        return 0U;
    }
    return s_frame[13] == SOFT_RESET_EOF ? 1U : 0U;
}

/**
 * @brief:  Build an A0 acknowledgement from the received message ID.
 * @param:  ack: Destination buffer with at least 14 bytes.
 * @retval: None.
 */
static void build_ack(uint8_t *ack) {
    uint8_t index;

    ack[0] = SOFT_RESET_SOF;
    ack[1] = SOFT_RESET_VERSION;
    ack[2] = s_frame[2];
    ack[3] = s_frame[3];
    ack[4] = SOFT_RESET_CMD_A0;
    ack[5] = SOFT_RESET_FLAG_ACK;
    ack[6] = SOFT_RESET_PAYLOAD_SIZE;
    ack[7] = 0U;
    for (index = 0U; index < SOFT_RESET_PAYLOAD_SIZE; index++) {
        ack[8U + index] = s_magic_key[index];
    }
    ack[12] = calculate_crc8(&ack[1], 11U);
    ack[13] = SOFT_RESET_EOF;
}

/**
 * @brief:  Pop one byte from the single-producer/single-consumer queue.
 * @param:  byte: Receives one queued byte.
 * @retval: 1 when a byte was returned, otherwise 0.
 */
static uint8_t pop_rx_byte(uint8_t *byte) {
    uint8_t tail = s_rx_tail;

    if (tail == s_rx_head) {
        return 0U;
    }
    *byte = s_rx_queue[tail];
    s_rx_tail = (uint8_t)((tail + 1U) & SOFT_RESET_QUEUE_MASK);
    return 1U;
}

/**
 * @brief:  Reset parser and receive-queue state.
 * @param:  None.
 * @retval: None.
 */
void soft_reset_init(void) {
    s_rx_head = 0U;
    s_rx_tail = 0U;
    s_rx_overflow = 0U;
    s_frame_length = 0U;
}

/**
 * @brief:  Queue one UART byte from the project-owned receive ISR.
 * @param:  byte: Received UART byte.
 * @retval: None.
 */
void soft_reset_rx_byte_isr(uint8_t byte) {
    uint8_t head = s_rx_head;
    uint8_t next = (uint8_t)((head + 1U) & SOFT_RESET_QUEUE_MASK);

    if (next == s_rx_tail) {
        s_rx_overflow = 1U;
        return;
    }
    s_rx_queue[head] = byte;
    s_rx_head = next;
}

/**
 * @brief:  Parse queued bytes and return at most one application action.
 * @param:  ack: Buffer for an A0 ACK; may be NULL.
 * @param:  ack_capacity: Size of ack in bytes.
 * @param:  ack_length: Receives the generated ACK length.
 * @retval: Requested action; the caller owns UART transmit and chip reset.
 */
soft_reset_action_t soft_reset_process(
    uint8_t *ack,
    uint8_t ack_capacity,
    uint8_t *ack_length
) {
    uint8_t byte;

    if (ack_length == NULL) {
        return SOFT_RESET_ACTION_NONE;
    }
    *ack_length = 0U;
    while (pop_rx_byte(&byte) != 0U) {
        if (s_frame_length == 0U && byte != SOFT_RESET_SOF) {
            continue;
        }
        s_frame[s_frame_length++] = byte;
        if (s_frame_length < SOFT_RESET_FRAME_SIZE) {
            continue;
        }
        s_frame_length = 0U;
        if (is_frame_valid() == 0U) {
            continue;
        }
        if (s_frame[4] == SOFT_RESET_CMD_A1) {
            return SOFT_RESET_ACTION_RESET;
        }
        if (s_frame[4] == SOFT_RESET_CMD_A0 &&
            (s_frame[5] & SOFT_RESET_FLAG_ACK) != 0U &&
            ack != NULL && ack_capacity >= SOFT_RESET_FRAME_SIZE) {
            build_ack(ack);
            *ack_length = SOFT_RESET_FRAME_SIZE;
            return SOFT_RESET_ACTION_SEND_ACK;
        }
    }
    return SOFT_RESET_ACTION_NONE;
}

/**
 * @brief:  Read and clear the receive-overflow flag.
 * @param:  None.
 * @retval: 1 when at least one ISR byte was dropped, otherwise 0.
 */
uint8_t soft_reset_take_overflow(void) {
    uint8_t overflow = s_rx_overflow;

    s_rx_overflow = 0U;
    return overflow;
}
