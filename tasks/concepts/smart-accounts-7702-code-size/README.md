# Delegated EOA code size

The user asks for EXTCODESIZE at a delegated EOA's address.
The check requires 23 bytes.

## The instruction

```text
After an EOA sets an EIP-7702 delegation to a contract, what does EXTCODESIZE return for the EOA's address? Just the number.
```

## What it touches

EIP-7702 stores a three-byte prefix followed by a twenty-byte delegate address on the EOA.
EXTCODESIZE reads that 23-byte indicator, even though calls execute the delegate's code.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `delegation_size_23` | Starts with 23 or twenty-three, with bytes as the optional unit | delegated account code |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Code-size checks can misclassify delegated EOAs if they assume that EOAs always have zero bytes of code.
[The final EIP-7702 text](https://eips.ethereum.org/EIPS/eip-7702) specifies the 23-byte EXTCODESIZE result.
