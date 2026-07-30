import { Nav } from './components/Nav'
import { Hero } from './components/Hero/Hero'
import { Pitch } from './components/Pitch'
import { Pipeline } from './components/Pipeline'
import { Differentiators } from './components/Differentiators'
import { DashboardMock } from './components/DashboardMock'
import { TechStack } from './components/TechStack'
import { Footer } from './components/Footer'

function App() {
  return (
    <main>
      <Nav />
      <Hero />
      <Pitch />
      <Pipeline />
      <Differentiators />
      <DashboardMock />
      <TechStack />
      <Footer />
    </main>
  )
}

export default App
