/******************************************************************************
 * @file:   soft_reset.h
 * @author: D_Lobster
 * @brief:  Transport-independent TS800X A0/A1 development protocol parser
 * @date:   2026-07-17
 ******************************************************************************/

#ifndef SOFT_RESET_H
#define SOFT_RESET_H

#include <stdint.h>

#define SOFT_RESET_FRAME_SIZE    14U

typedef enum {
    SOFT_RESET_ACTION_NONE = 0,
    SOFT_RESET_ACTION_SEND_ACK,
    SOFT_RESET_ACTION_RESET
} soft_reset_action_t;

/**
 * @brief:  Reset parser and receive-queue state.
 * @param:  None.
 * @retval: None.
 */
void soft_reset_init(void);

/**
 * @brief:  Queue one UART byte from the project-owned receive ISR.
 * @param:  byte: Received UART byte.
 * @retval: None. A full queue drops the byte and records overflow.
 */
void soft_reset_rx_byte_isr(uint8_t byte);

/**
 * @brief:  Parse queued bytes and return at most one application action.
 * @param:  ack: Buffer for an A0 ACK; may be NULL when no ACK can be sent.
 * @param:  ack_capacity: Size of ack in bytes.
 * @param:  ack_length: Receives 14 for SEND_ACK and 0 otherwise.
 * @retval: Requested action. The caller owns UART transmit and chip reset.
 */
soft_reset_action_t soft_reset_process(
    uint8_t *ack,
    uint8_t ack_capacity,
    uint8_t *ack_length
);

/**
 * @brief:  Read and clear the receive-overflow flag.
 * @param:  None.
 * @retval: 1 when at least one ISR byte was dropped, otherwise 0.
 */
uint8_t soft_reset_take_overflow(void);

#endif /* SOFT_RESET_H */
