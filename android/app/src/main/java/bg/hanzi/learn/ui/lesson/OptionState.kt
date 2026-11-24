package bg.hanzi.learn.ui.lesson

/**
 * How an answer option is drawn after the learner has answered.
 *
 * The state is a PLAIN FUNCTION of three facts, so it can be tested
 * without a device -- and it had to be a plain function, because the
 * version that lived in the Composable painted EVERY option red when
 * the learner was wrong, the right answer included. The learner was
 * shown four red buttons and the correct meaning in a small line of
 * text under them, and had to work out for themselves which one was
 * right.
 */
enum class OptionState {
    /** Not answered yet: nothing is marked. */
    NONE,

    /** The right answer: it is marked as right. */
    RIGHT,

    /** The answer the learner chose, and it was wrong. */
    WRONG,
}

/**
 * The state of ONE option of a RECOGNISE card.
 *
 * @param answered whether the learner has answered the card
 * @param isRight whether THIS option is the right one
 * @param isChosen whether THIS option is the one the learner picked
 */
fun optionState(
    answered: Boolean,
    isRight: Boolean,
    isChosen: Boolean,
): OptionState = when {
    !answered -> OptionState.NONE
    // The right answer comes first: when the learner picked it, it is
    // the right answer AND the chosen one, and it has to be shown as
    // the right answer.
    isRight -> OptionState.RIGHT
    isChosen -> OptionState.WRONG
    else -> OptionState.NONE
}
