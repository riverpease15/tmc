if (pins.digitalReadPin(DigitalPin.P0) < 1000 && input.buttonIsPressed(Button.A)) {
    basic.showIcon(IconNames.No)
} else {
    radio.sendString("HI")
}