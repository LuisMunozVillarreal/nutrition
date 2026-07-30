import { Given } from '@badeball/cypress-cucumber-preprocessor'
import { loginAsE2eUser } from '../e2eCredentials'

Given('I am logged in', () => {
  loginAsE2eUser('regular')
})

Given('I am logged in as staff', () => {
  loginAsE2eUser('staff')
})
