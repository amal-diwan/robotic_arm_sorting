#include <ESP32Servo.h>

// =====================
// Servo pins
// =====================
const int BASE_PIN      = 12;
const int LEFT_ARM_PIN  = 13;  // up and down
const int RIGHT_ARM_PIN = 5;   // forward and backward
const int CLAW_PIN      = 23;

// =====================
// Servo objects
// =====================
Servo baseServo;
Servo leftServo;
Servo rightServo;
Servo clawServo;

// =====================
// Your tested safe angle limits
// =====================
const int BASE_MIN  = 0;
const int BASE_MAX  = 140;

const int LEFT_MIN  = 50;
const int LEFT_MAX  = 90;

const int RIGHT_MIN = 70;
const int RIGHT_MAX = 120;

const int CLAW_MIN  = 0;
const int CLAW_MAX  = 50;

// =====================
// Final positions
// Adjust these if needed
// =====================

// Base rotation positions
const int BASE_PICK   = 0;
const int BASE_ORANGE = 45;
const int BASE_GRAY   = 90;
const int BASE_BLACK  = 140;

// Left servo = up/down
const int LEFT_UP   = 50;
const int LEFT_DOWN = 90;

// Right servo = forward/backward
const int RIGHT_BACK    = 70;
const int RIGHT_FORWARD = 110;

// Claw
const int CLAW_OPEN   = 20;
const int CLAW_CLOSED = 0;

// Current positions
int currentBase  = BASE_PICK;
int currentLeft  = LEFT_UP;
int currentRight = RIGHT_BACK;
int currentClaw  = CLAW_OPEN;

// Movement speed
const int STEP_DELAY = 15;

void setup() {
  Serial.begin(115200);
  delay(1000);

  baseServo.setPeriodHertz(50);
  leftServo.setPeriodHertz(50);
  rightServo.setPeriodHertz(50);
  clawServo.setPeriodHertz(50);

  baseServo.attach(BASE_PIN, 500, 2400);
  leftServo.attach(LEFT_ARM_PIN, 500, 2400);
  rightServo.attach(RIGHT_ARM_PIN, 500, 2400);
  clawServo.attach(CLAW_PIN, 500, 2400);

  goHome();

  Serial.println();
  Serial.println("Corrected Final Cube Sorting Robot Ready");
  Serial.println("-----------------------------------------");
  Serial.println("Left servo  = up/down");
  Serial.println("Right servo = forward/backward");
  Serial.println();
  Serial.println("Commands:");
  Serial.println("O = sort orange");
  Serial.println("G = sort gray");
  Serial.println("B = sort black");
  Serial.println("H = home");
  Serial.println();
  Serial.println("Serial Monitor: 115200 baud, Newline");
}

void loop() {
  if (Serial.available()) {
    char command = Serial.read();

    if (command == '\n' || command == '\r') {
      return;
    }

    command = toupper(command);

    if (command == 'O') {
      Serial.println("Sorting ORANGE cube");
      sortCube(BASE_ORANGE);
    }
    else if (command == 'G') {
      Serial.println("Sorting GRAY cube");
      sortCube(BASE_GRAY);
    }
    else if (command == 'B') {
      Serial.println("Sorting BLACK cube");
      sortCube(BASE_BLACK);
    }
    else if (command == 'H') {
      Serial.println("Going home");
      goHome();
    }
    else {
      Serial.println("Unknown command. Use O, G, B, or H.");
    }
  }
}

// =====================
// Main sorting sequence
// =====================
void sortCube(int dropBaseAngle) {
  // Start safe
  goHome();
  delay(500);

  // Move to pickup location
  moveBase(BASE_PICK);
  delay(300);

  // Reach forward to cube
  moveForward();
  delay(400);

  // Lower arm
  moveDown();
  delay(400);

  // Grab cube
  closeClaw();
  delay(600);

  // Lift cube
  moveUp();
  delay(400);

  // Pull cube backward
  moveBack();
  delay(400);

  // Rotate to correct bin
  moveBase(dropBaseAngle);
  delay(500);

  // Move forward over bin
  moveForward();
  delay(400);

  // Optional: lower a little before drop
  moveDown();
  delay(300);

  // Release cube
  openClaw();
  delay(600);

  // Lift up and pull back
  moveUp();
  delay(300);
  moveBack();
  delay(300);

  // Return base to pickup
  moveBase(BASE_PICK);
  delay(300);

  Serial.println("Sorting complete.");
  printPositions();
}

// =====================
// Home position
// =====================
void goHome() {
  openClaw();
  moveUp();
  moveBack();
  moveBase(BASE_PICK);

  Serial.println("Home position");
  printPositions();
}

// =====================
// Base movement
// =====================
void moveBase(int targetAngle) {
  targetAngle = constrain(targetAngle, BASE_MIN, BASE_MAX);

  moveServoSmooth(baseServo, currentBase, targetAngle);
  currentBase = targetAngle;
}

// =====================
// Left servo movement
// Left = up/down
// =====================
void moveUp() {
  moveLeft(LEFT_UP);
}

void moveDown() {
  moveLeft(LEFT_DOWN);
}

void moveLeft(int targetAngle) {
  targetAngle = constrain(targetAngle, LEFT_MIN, LEFT_MAX);

  moveServoSmooth(leftServo, currentLeft, targetAngle);
  currentLeft = targetAngle;
}

// =====================
// Right servo movement
// Right = forward/backward
// =====================
void moveForward() {
  moveRight(RIGHT_FORWARD);
}

void moveBack() {
  moveRight(RIGHT_BACK);
}

void moveRight(int targetAngle) {
  targetAngle = constrain(targetAngle, RIGHT_MIN, RIGHT_MAX);

  moveServoSmooth(rightServo, currentRight, targetAngle);
  currentRight = targetAngle;
}

// =====================
// Claw movement
// =====================
void openClaw() {
  moveClaw(CLAW_OPEN);
}

void closeClaw() {
  moveClaw(CLAW_CLOSED);
}

void moveClaw(int targetAngle) {
  targetAngle = constrain(targetAngle, CLAW_MIN, CLAW_MAX);

  moveServoSmooth(clawServo, currentClaw, targetAngle);
  currentClaw = targetAngle;
}

// =====================
// Smooth servo movement
// =====================
void moveServoSmooth(Servo &servo, int startAngle, int endAngle) {
  if (startAngle < endAngle) {
    for (int pos = startAngle; pos <= endAngle; pos++) {
      servo.write(pos);
      delay(STEP_DELAY);
    }
  } else {
    for (int pos = startAngle; pos >= endAngle; pos--) {
      servo.write(pos);
      delay(STEP_DELAY);
    }
  }
}

// =====================
// Debug printing
// =====================
void printPositions() {
  Serial.println();
  Serial.print("Base: ");
  Serial.println(currentBase);

  Serial.print("Left up/down: ");
  Serial.println(currentLeft);

  Serial.print("Right forward/back: ");
  Serial.println(currentRight);

  Serial.print("Claw: ");
  Serial.println(currentClaw);

  Serial.println();
}